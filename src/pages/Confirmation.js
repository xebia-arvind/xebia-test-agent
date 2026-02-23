function Confirmation() {
    const orders =
        JSON.parse(localStorage.getItem("orders")) || [];

    const latestOrder = orders[orders.length - 1];

    return (
        <div className="container mt-5">
            <div className="alert alert-success">
                <h2>🎉 Payment Successful!</h2>
                <p>Order ID: {latestOrder?.id}</p>
                <p>Date: {latestOrder?.date}</p>
                <p>Total Paid: ₹{latestOrder?.total}</p>
            </div>
        </div>
    );
}

export default Confirmation;
