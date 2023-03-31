import './Carousel.css'

function Carousel() {
    const swiper = new Swiper('.swiper', {
        // Optional parameters
        direction: 'horizontal',
        loop: true,
      
        // Navigation arrows
        navigation: {
          nextEl: '.swiper-button-next',
          prevEl: '.swiper-button-prev',
        }
    });
    return(
        <div>
            <h1>Our models</h1>
            <div class="swiper">
            <div class="swiper-wrapper">
                <div class="swiper-slide">Long short-term memory neural networks</div>
                <div class="swiper-slide">Recurrent neural networks</div>
                <div class="swiper-slide">Multi-layer perceptions</div>
                <div class="swiper-slide">Decision trees</div>
            </div>
            
            <div class="swiper-button-prev"></div>
            <div class="swiper-button-next"></div>
          </div>
        </div>
    )
}

export default Carousel