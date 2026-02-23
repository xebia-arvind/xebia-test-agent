import React, { createContext, useState, useEffect } from "react";

export const CartContext = createContext();

export const CartProvider = ({ children }) => {
    const [cart, setCart] = useState(
        JSON.parse(localStorage.getItem("cart")) || []
    );

    useEffect(() => {
        localStorage.setItem("cart", JSON.stringify(cart));
    }, [cart]);

    const addToCart = (product) => {
        const existing = cart.find((item) => item.id === product.id);

        if (existing) {
            setCart(
                cart.map((item) =>
                    item.id === product.id
                        ? { ...item, quantity: item.quantity + 1 }
                        : item
                )
            );
        } else {
            setCart([...cart, { ...product, quantity: 1 }]);
        }
    };

    const updateQuantity = (id, qty) => {
        if (qty <= 0) return;
        setCart(
            cart.map((item) =>
                item.id === id ? { ...item, quantity: qty } : item
            )
        );
    };

    const removeItem = (id) => {
        setCart(cart.filter((item) => item.id !== id));
    };

    const clearCart = () => {
        setCart([]);
    };

    const saveOrder = (orderData) => {
        const existingOrders =
            JSON.parse(localStorage.getItem("orders")) || [];

        localStorage.setItem(
            "orders",
            JSON.stringify([...existingOrders, orderData])
        );
    };

    return (
        <CartContext.Provider
            value={{ cart, addToCart, updateQuantity, removeItem, clearCart, saveOrder }}
        >
            {children}
        </CartContext.Provider>
    );
};
