import products from "../data/products.json";
import ProductCard from "../components/ProductCard";
import HeroCarousel from "../components/HeroCarousel";

function Home() {
    return (
        <div className="container mt-4">
            <HeroCarousel />
            <h2 className="mb-4">Explore Products</h2>
            <div className="row">
                {products.map((product) => (
                    <ProductCard key={product.id} product={product} />
                ))}
            </div>
        </div>
    );
}

export default Home;
