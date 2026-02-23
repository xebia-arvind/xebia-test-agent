import { useParams } from "react-router-dom";
import products from "../data/products.json";
import { useContext, useState } from "react";
import { CartContext } from "../context/CartContext";

function ProductDetail() {
    const { id } = useParams();
    const { addToCart } = useContext(CartContext);
    const [animate, setAnimate] = useState(false);

    const product = products.find((p) => p.id === parseInt(id));

    const handleAdd = () => {
        addToCart(product);
        setAnimate(true);

        setTimeout(() => {
            setAnimate(false);
        }, 400);
    };

    return (
        <div className="container mt-4">
            <div className="row">
                <div className="col-md-6">
                    <img
                        src={product.image}
                        className="img-fluid rounded shadow"
                        alt={product.name}
                    />
                </div>

                <div className="col-md-6">
                    <h2>{product.name}</h2>
                    <p>{product.description}</p>
                    <h4 className="text-success">₹{product.price}</h4>

                    <button
                        className={`btn btn-primary ${animate ? "added-animation" : ""
                            }`}
                        onClick={handleAdd}
                    >
                        Add to Cart
                    </button>
                </div>
            </div>
        </div>
    );
}

export default ProductDetail;
