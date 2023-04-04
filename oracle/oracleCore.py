from __future__ import annotations
import sys
import base64
from flask import Flask, request
import os
import json
from oracle import models, dataManager
from common import utils


class OracleState:
    """Allows for the client state to persist between classes"""

    SECRET = ""
    monitor: OracleTransactionMonitor = None

    @classmethod
    def init(cls):
        with open(".creds/test_oracle_creds", "r") as file:
            file.readline() # throw out address as it is not needed
            cls.SECRET = file.readline().strip("\n")

        cls.monitor = OracleTransactionMonitor()


class Pricing:
    """Class to keep track and modify the pricing of transactions"""
    mult_cache = {}

    @classmethod
    def calc_ds_usage_incentive(cls, size: int, loss: float):
        """Calculates and returns the reward for a database being used in a model"""
        mult, txn_id = cls.get_price_multiplier(utils.OpCodes.DS_INCENTIVE)
        return int(size * mult / loss), txn_id

    @classmethod
    def calc_model_usage_incentive(cls, loss: float):
        """Calculates and returns the reward for a model being used"""
        mult, txn_id = cls.get_price_multiplier(utils.OpCodes.MODEL_INCENTIVE)
        return int(mult / loss), txn_id

    @classmethod
    def calc_dataset_upload_price(cls, size: int):
        """Calculates and returns the latest price and the txn_id where it was changed"""
        mult, txn_id = cls.get_price_multiplier(utils.OpCodes.UP_DATASET)
        return int(size * mult), txn_id

    @classmethod
    def calc_model_train_price(cls, raw_model: str, dataset_name: str, **kwargs):
        """Calculates and returns the latest price and the txn_id where it was changed"""
        mult, txn_id = cls.get_price_multiplier(utils.OpCodes.TRAIN_MODEL)
        model = models.PredictModel.create(raw_model, **kwargs)
        dataset = dataManager.database.get(dataset_name)
        return int(model.model_complexity * mult * dataset["size"]), txn_id

    @classmethod
    def calc_model_query_price(cls, model_name: str):
        """Calculates and returns the latest price and the txn_id where it was changed"""
        mult, txn_id = cls.get_price_multiplier(utils.OpCodes.QUERY_MODEL)
        model = models.get_trained_model(model_name)[0]
        return int(model.model_complexity * mult), txn_id

    @classmethod
    def get_price_multiplier(cls, mul_op: str) -> tuple[float, str]:
        """Gets the price multiplier from the database and returns it and the txn_id where it was last changed"""
        if not cls.mult_cache.get(mul_op):
            cls.mult_cache[mul_op] = dataManager.database.hgetall("<PRICE>" + mul_op)

        return cls.mult_cache[mul_op]["mul"], cls.mult_cache[mul_op]["txn_id"]

    @classmethod
    def set_price_multiplier(cls, mul_op: str, new_mul: float):
        """Sends an update txn.  Stores txn_id and the new price multiplier in the database"""
        op = utils.OpCodes.UPDATE_PRICE  # op is included in locals() and is passed inside the note
        txn_id = utils.transact(utils.ORACLE_ALGO_ADDRESS, OracleState.SECRET, utils.ORACLE_ALGO_ADDRESS, 0,
                             note=json.dumps(utils.flatten_locals(locals())))

        cls.mult_cache[mul_op] = {"mul_op": mul_op, "mul": new_mul, "txn_id": txn_id}
        # Save txn_id to database
        dataManager.database.hset("<PRICE>" + mul_op, mapping={"mul_op": mul_op, "mul": new_mul, "txn_id": txn_id})


class OracleTransactionMonitor(utils.TransactionMonitor):
    """Keeps the oracle updated on incoming transactions from users, real world events"""

    def __init__(self, all_time=False):
        super(OracleTransactionMonitor, self).__init__(utils.ORACLE_ALGO_ADDRESS, all_time=all_time)

    def process_incoming(self, txn):
        """Execute operations based on the OP code of the incoming transaction"""
        txn["note"] = json.loads(base64.b64decode(txn["note"]).decode())
        # Split into OP and ARGS
        op = txn["note"].pop("op")
        kwargs: dict = {**txn["note"].pop("kwargs"), **txn["note"]}

        match op:
            case utils.OpCodes.UP_DATASET:
                return dataManager.save_dataset(**kwargs, txn_id=txn["id"], user_id=txn["sender"])

            case utils.OpCodes.QUERY_MODEL:
                model, meta, ds_meta = models.get_trained_model(kwargs["model_name"])
                out = model(kwargs["model_input"])
                loss_fn = models.PredictModel.get_loss_fn(model.loss_fn_name)

                # TODO: Get result from outside world
                loss = loss_fn(out, target)
                # Reward model trainer
                utils.transact(utils.ORACLE_ALGO_ADDRESS, OracleState.SECRET, meta[1],
                               Pricing.calc_model_usage_incentive(loss)[0],
                               note=json.dumps({"op": utils.OpCodes.MODEL_INCENTIVE, "model_name": model.model_name}))
                # Reward dataset uploader
                utils.transact(utils.ORACLE_ALGO_ADDRESS, OracleState.SECRET, ds_meta[1],
                               Pricing.calc_ds_usage_incentive(dataManager.load_dataset(model.data_handler.dataset_name), loss)[0],
                               note=json.dumps({"op": utils.OpCodes.DS_INCENTIVE, "dataset_name": model.data_handler.dataset_name}))

                # Report result back to the user
                utils.transact(utils.ORACLE_ALGO_ADDRESS, OracleState.SECRET, txn["sender"], 0,
                               note=json.dumps({"op": utils.OpCodes.RESPONSE, "query_result": out}))

            case utils.OpCodes.UPDATE_PRICE:
                # Handle any additional price change logic here if needed
                ...

            case utils.OpCodes.TRAIN_MODEL:
                handler, dataset_attribs = dataManager.load_dataset(kwargs["dataset_name"])
                model = models.PredictModel.create(**kwargs, data_handler=handler)
                accuracy, loss = model.train_model(**kwargs)

                utils.transact(utils.ORACLE_ALGO_ADDRESS, OracleState.SECRET, dataset_attribs["user_id"],
                               Pricing.calc_ds_usage_incentive(dataManager.load_dataset(model.data_handler.dataset_name), loss)[0],
                               note=json.dumps({"op": utils.OpCodes.DS_INCENTIVE, "dataset_name": model.data_handler.dataset_name}))

                models.save_trained_model(model, f"models/{kwargs['new_model']}", txn["id"], txn["sender"])


app = Flask(__name__)


@app.route('/ping', methods=["GET"])
def ping():
    """Accepts pings to report that the oracle is running properly"""
    return {"pinged": "oracle"}


@app.route('/dataset_upload_price', methods=["GET"])
def report_dataset_upload_price():
    """Report back the latest dataset upload price"""
    price, txn_id = Pricing.calc_dataset_upload_price(**request.args)
    return {"price": price, "txn_id": txn_id}


@app.route('/model_train_price', methods=["GET"])
def report_model_train_price():
    """Report back the latest training price"""
    price, txn_id = Pricing.calc_model_train_price(**request.args)
    return {"price": price, "txn_id": txn_id}


@app.route('/model_query_price', methods=["GET"])
def report_model_query_price():
    """Report back the latest query price"""
    price, txn_id = Pricing.calc_model_query_price(**request.args)
    return {"price": price, "txn_id": txn_id}
