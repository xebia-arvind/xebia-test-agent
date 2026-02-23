import products from "../data/products.json";
import ProductCard from "../components/ProductCard";

function Home() {
    return (
        <div className="container mt-4">
            <h2 className="mb-4">Products</h2>
            <div className="row">
                {products.map((product) => (
                    <ProductCard key={product.id} product={product} />
                ))}
            </div>
        </div>
    );
}

export default Home;
