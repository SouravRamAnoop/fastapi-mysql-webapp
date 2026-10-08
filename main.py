from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import List

import models
from database import engine, get_db
import schemas

# Create database tables automatically
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Simple E-Commerce App")

# Serve static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")

# Using pbkdf2_sha256 avoids any 72-byte limit issues present in bcrypt
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Routes to serve frontend pages
@app.get("/")
def read_index():
    return FileResponse("templates/index.html")

@app.get("/login")
def read_login():
    return FileResponse("templates/login.html")

@app.get("/cart")
def read_cart():
    return FileResponse("templates/cart.html")

@app.get("/orders")
def read_orders():
    return FileResponse("templates/orders.html")

@app.get("/admin")
def read_admin():
    return FileResponse("templates/admin.html")

# --- AUTHENTICATION ---
@app.post("/api/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pw = hash_password(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_pw,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/api/login", response_model=schemas.UserResponse)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return user

# --- PRODUCTS ---
@app.get("/api/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()

@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/api/products", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    new_prod = models.Product(**product.dict())
    db.add(new_prod)
    db.commit()
    db.refresh(new_prod)
    return new_prod

@app.put("/api/products/{product_id}", response_model=schemas.ProductResponse)
def update_product(product_id: int, product: schemas.ProductCreate, db: Session = Depends(get_db)):
    prod = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.dict().items():
        setattr(prod, key, value)
    db.commit()
    db.refresh(prod)
    return prod

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    prod = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(prod)
    db.commit()
    return {"message": "Product deleted successfully"}

# --- CART ---
@app.get("/api/cart/{user_id}", response_model=List[schemas.CartItemResponse])
def get_cart(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Cart).filter(models.Cart.user_id == user_id).all()

@app.post("/api/cart/{user_id}")
def add_to_cart(user_id: int, item: schemas.CartAdd, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.quantity < item.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    cart_item = db.query(models.Cart).filter(
        models.Cart.user_id == user_id, 
        models.Cart.product_id == item.product_id
    ).first()

    if cart_item:
        cart_item.quantity += item.quantity
    else:
        cart_item = models.Cart(user_id=user_id, product_id=item.product_id, quantity=item.quantity)
        db.add(cart_item)
    
    db.commit()
    return {"message": "Added to cart successfully"}

@app.put("/api/cart/item/{cart_id}")
def update_cart_item(cart_id: int, update: schemas.CartUpdate, db: Session = Depends(get_db)):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    if update.quantity <= 0:
        db.delete(cart_item)
    else:
        if cart_item.product.quantity < update.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        cart_item.quantity = update.quantity
    
    db.commit()
    return {"message": "Cart updated"}

@app.delete("/api/cart/item/{cart_id}")
def remove_cart_item(cart_id: int, db: Session = Depends(get_db)):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(cart_item)
    db.commit()
    return {"message": "Item removed from cart"}

# --- ORDERS ---
@app.post("/api/orders/{user_id}", response_model=schemas.OrderResponse)
def checkout(user_id: int, db: Session = Depends(get_db)):
    cart_items = db.query(models.Cart).filter(models.Cart.user_id == user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    total_amount = 0
    for item in cart_items:
        if item.product.quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"Product {item.product.name} is out of stock")
        total_amount += item.product.price * item.quantity

    # Create order
    new_order = models.Order(user_id=user_id, total_amount=total_amount, status="Pending")
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # Add order items and deduct stock
    for item in cart_items:
        order_item = models.OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.product.price
        )
        item.product.quantity -= item.quantity
        db.add(order_item)
        db.delete(item)

    db.commit()
    db.refresh(new_order)
    return new_order

@app.get("/api/orders/user/{user_id}", response_model=List[schemas.OrderResponse])
def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Order).filter(models.Order.user_id == user_id).all()

@app.get("/api/orders", response_model=List[schemas.OrderResponse])
def get_all_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).all()

@app.put("/api/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, status_update: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = status_update.status
    db.commit()
    db.refresh(order)
    return order

# --- ADMIN USERS ---
@app.get("/api/users", response_model=List[schemas.UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()