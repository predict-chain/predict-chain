import React, {useState, useEffect} from 'react';
import axios from 'axios'

function FlaskTest() {
  const [getMessage, setGetMessage] = useState({})

  useEffect(()=>{
    axios.get('http://localhost:5000/flask/hello').then(response => {
      console.log("SUCCESS", response)
      setGetMessage(response)
    }).catch(error => {
      console.log(error)
    })

  }, [])
  
  return (
    <div>
        {getMessage.status === 200 ? 
        <h3>{getMessage.data.message}</h3> :
        <h3>LOADING</h3>}
    </div>
  );
}

export default FlaskTest;
