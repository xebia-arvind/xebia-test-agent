import React, { createContext, useState, useEffect } from "react";

export const CartContext = createContext();

export const CartProvider = ({ children }) => {
    const [cart, setCart] = useState(
        JSON.parse(localStorage.getItem("cart")) || []
    );
    const [wishlist, setWishlist] = useState(
        JSON.parse(localStorage.getItem("wishlist")) || []
    );
    const [appliedCoupon, setAppliedCoupon] = useState(
        JSON.parse(localStorage.getItem("coupon")) || null
    );

    useEffect(() => {
        localStorage.setItem("cart", JSON.stringify(cart));
    }, [cart]);

    useEffect(() => {
        localStorage.setItem("wishlist", JSON.stringify(wishlist));
    }, [wishlist]);

    useEffect(() => {
        localStorage.setItem("coupon", JSON.stringify(appliedCoupon));
    }, [appliedCoupon]);

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

    const applyCoupon = (code) => {
        const coupons = {
            "SAVE10": { code: "SAVE10", type: "PERCENT", value: 10 },
            "HOTDEAL": { code: "HOTDEAL", type: "FLAT", value: 1000, minPurchase: 3000 },
            "FIRSTORDER": { code: "FIRSTORDER", type: "PERCENT", value: 20 }
        };

        const coupon = coupons[code.toUpperCase()];
        if (!coupon) {
            throw new Error("Invalid coupon code");
        }

        const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
        if (coupon.minPurchase && subtotal < coupon.minPurchase) {
            throw new Error(`Minimum purchase of ₹${coupon.minPurchase} required for this coupon.`);
        }

        setAppliedCoupon(coupon);
        return coupon;
    };

    const removeCoupon = () => {
        setAppliedCoupon(null);
    };

    const isWishlisted = (id) => {
        return wishlist.some((item) => item.id === id);
    };

    const addToWishlist = (product) => {
        if (!product) return;
        if (wishlist.some((item) => item.id === product.id)) return;
        setWishlist([...wishlist, product]);
    };

    const removeFromWishlist = (id) => {
        setWishlist(wishlist.filter((item) => item.id !== id));
    };

    const toggleWishlist = (product) => {
        if (!product) return;
        if (isWishlisted(product.id)) {
            removeFromWishlist(product.id);
            return;
        }
        addToWishlist(product);
    };

    const moveWishlistToCart = (id) => {
        const product = wishlist.find((item) => item.id === id);
        if (!product) return;
        addToCart(product);
        removeFromWishlist(id);
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
            value={{
                cart,
                wishlist,
                appliedCoupon,
                addToCart,
                updateQuantity,
                removeItem,
                clearCart,
                saveOrder,
                isWishlisted,
                addToWishlist,
                removeFromWishlist,
                toggleWishlist,
                moveWishlistToCart,
                applyCoupon,
                removeCoupon,
            }}
        >
            {children}
        </CartContext.Provider>
    );
};
