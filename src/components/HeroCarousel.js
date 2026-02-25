import React from 'react';
import { Link } from 'react-router-dom';

const HeroCarousel = () => {
    const slides = [
        {
            id: 1,
            image: "https://images.unsplash.com/photo-1498050108023-c5249f4df085?q=80&w=2072&auto=format&fit=crop",
            title: "Flash Sale: Electronics",
            subtitle: "Up to 50% off on latest gadgets and accessories.",
            cta: "Shop Gadgets",
            link: "/",
            badge: "Limited Time"
        },
        {
            id: 2,
            image: "https://images.unsplash.com/photo-1441986300917-64674bd600d8?q=80&w=2070&auto=format&fit=crop",
            title: "New Arrivals: Lifestyle",
            subtitle: "Discover our curated collection of premium essentials.",
            cta: "Explore Now",
            link: "/",
            badge: "Summer 2026"
        },
        {
            id: 3,
            image: "https://images.unsplash.com/photo-1445205170230-053b83016050?q=80&w=2071&auto=format&fit=crop",
            title: "Trending Fashion",
            subtitle: "Elevate your style with the season's hottest picks.",
            cta: "View Collection",
            link: "/",
            badge: "Fashion Week"
        }
    ];

    return (
        <div id="heroCarousel" className="carousel slide hero-carousel mb-5" data-bs-ride="carousel">
            <div className="carousel-indicators">
                {slides.map((_, index) => (
                    <button
                        key={index}
                        type="button"
                        data-bs-target="#heroCarousel"
                        data-bs-slide-to={index}
                        className={index === 0 ? "active" : ""}
                        aria-current={index === 0 ? "true" : "false"}
                        aria-label={`Slide ${index + 1}`}
                    ></button>
                ))}
            </div>
            <div className="carousel-inner">
                {slides.map((slide, index) => (
                    <div key={slide.id} className={`carousel-item ${index === 0 ? "active" : ""}`}>
                        <div className="carousel-img-wrapper">
                            <img src={slide.image} className="d-block w-100 h-100" alt={slide.title} />
                            <div className="carousel-overlay"></div>
                        </div>
                        <div className="carousel-caption d-none d-md-block text-start">
                            <span className="badge bg-danger mb-3 py-2 px-3 text-uppercase">{slide.badge}</span>
                            <h1 className="display-4 fw-bold mb-3">{slide.title}</h1>
                            <p className="fs-5 mb-4 text-light-50">{slide.subtitle}</p>
                            <Link to={slide.link} className="btn btn-primary btn-lg px-5 py-3 rounded-pill fw-bold shadow-lg">
                                {slide.cta}
                            </Link>
                        </div>
                    </div>
                ))}
            </div>
            <button className="carousel-control-prev" type="button" data-bs-target="#heroCarousel" data-bs-slide="prev">
                <span className="carousel-control-prev-icon" aria-hidden="true"></span>
                <span className="visually-hidden">Previous</span>
            </button>
            <button className="carousel-control-next" type="button" data-bs-target="#heroCarousel" data-bs-slide="next">
                <span className="carousel-control-next-icon" aria-hidden="true"></span>
                <span className="visually-hidden">Next</span>
            </button>
        </div>
    );
};

export default HeroCarousel;
