from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psycopg2
import os
from dotenv import load_dotenv
from typing import List
import shutil
import uuid

load_dotenv()

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = os.getenv("BASE_URL")

# ✅ Create uploads folder
if not os.path.exists("uploads"):
    os.makedirs("uploads")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# -----------------------------
# ✅ DB Connection
# -----------------------------
def get_connection():
    try:
        return psycopg2.connect(
            DATABASE_URL,
            sslmode="require"
        )
    except Exception as e:
        print("Database connection error:", e)
        raise HTTPException(status_code=500, detail="Database connection failed")


# -----------------------------
# ✅ Upload Image
# -----------------------------
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_location = f"uploads/{unique_filename}"

        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {"filename": unique_filename}

    except Exception as e:
        print("UPLOAD ERROR:", e)
        raise HTTPException(status_code=400, detail="Image upload failed")


# -----------------------------
# ✅ Models
# -----------------------------
class UserRegister(BaseModel):
    name: str
    email: str
    phone: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class CategoryCreate(BaseModel):
    name: str
    image: str | None = None


class ProductCreate(BaseModel):
    name: str
    price: float
    image_url: str
    category_id: str


class OrderItem(BaseModel):
    product_id: str
    quantity: int


class OrderCreate(BaseModel):
    user_id: str
    total_amount: float
    items: List[OrderItem]


class OrderStatusUpdate(BaseModel):
    status: str


# -----------------------------
# ✅ Root
# -----------------------------
@app.get("/")
def root():
    return {"message": "Grocery API Running ✅"}


# -----------------------------
# ✅ Register
# -----------------------------
@app.post("/register")
def register(user: UserRegister):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (name, email, phone, password) VALUES (%s,%s,%s,%s)",
            (user.name, user.email, user.phone, user.password),
        )
        conn.commit()
        return {"message": "User Registered Successfully ✅"}
    except:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ Login
# -----------------------------
@app.post("/login")
def login(user: UserLogin):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name FROM users WHERE email=%s AND password=%s",
            (user.email, user.password),
        )
        data = cur.fetchone()

        if data:
            return {
                "message": "Login Success ✅",
                "user_id": str(data[0]),
                "name": data[1]
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid Credentials")
    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ Categories
# -----------------------------
@app.get("/categories")
def get_categories():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name, image FROM categories")
        rows = cur.fetchall()

        return [
            {
                "id": str(row[0]),
                "name": row[1],
                "image": f"{BASE_URL}/uploads/{row[2]}" if row[2] else None
            }
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()


@app.post("/add-category")
def add_category(category: CategoryCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO categories (name, image) VALUES (%s,%s)",
            (category.name, category.image),
        )
        conn.commit()
        return {"message": "Category Added ✅"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ Products
# -----------------------------
@app.get("/products/{category_id}")
def get_products(category_id: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, price, image_url FROM products WHERE category_id=%s",
            (category_id,),
        )
        rows = cur.fetchall()

        return [
            {
                "id": str(row[0]),
                "name": row[1],
                "price": float(row[2]),
                "image_url": f"{BASE_URL}/uploads/{row[3]}" if row[3] else None
            }
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()


@app.post("/add-product")
def add_product(product: ProductCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO products (name, price, image_url, category_id) VALUES (%s,%s,%s,%s)",
            (product.name, product.price, product.image_url, product.category_id),
        )
        conn.commit()
        return {"message": "Product Added ✅"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ Orders
# -----------------------------
@app.post("/place-order")
def place_order(order: OrderCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO orders (user_id, total_amount, status) VALUES (%s,%s,%s) RETURNING id",
            (order.user_id, order.total_amount, "Placed"),
        )
        order_id = cur.fetchone()[0]

        for item in order.items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s,%s,%s)",
                (order_id, item.product_id, item.quantity),
            )

        conn.commit()

        return {
            "message": "Order Placed ✅",
            "order_id": str(order_id)
        }

    finally:
        cur.close()
        conn.close()


@app.get("/orders/{user_id}")
def get_orders(user_id: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT o.id, o.total_amount, o.status, o.created_at, p.image_url
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC
        """, (user_id,))
        rows = cur.fetchall()

        orders = {}
        for row in rows:
            order_id = str(row[0])
            if order_id not in orders:
                orders[order_id] = {
                    "order_id": order_id,
                    "total_amount": float(row[1]),
                    "status": row[2],
                    "date": str(row[3]),
                    "product_image": f"{BASE_URL}/uploads/{row[4]}" if row[4] else None
                }

        return list(orders.values())

    finally:
        cur.close()
        conn.close()

        # -----------------------------
# ✅ ADMIN: Get All Orders
# -----------------------------
@app.get("/admin/orders")
def get_all_orders():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                o.id,
                u.name,
                o.total_amount,
                o.status,
                o.created_at
            FROM orders o
            JOIN users u ON o.user_id = u.id
            ORDER BY o.created_at DESC
        """)
        rows = cur.fetchall()

        return [
            {
                "order_id": str(row[0]),
                "customer_name": row[1],
                "total_amount": float(row[2]),
                "status": row[3],
                "date": str(row[4])
            }
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ ADMIN: Update Order Status
# -----------------------------
@app.put("/admin/update-order-status/{order_id}")
def update_order_status(order_id: str, status_update: OrderStatusUpdate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE orders SET status=%s WHERE id=%s",
            (status_update.status, order_id),
        )

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order not found")

        conn.commit()

        return {"message": "Order Status Updated ✅"}

    finally:
        cur.close()
        conn.close()


# -----------------------------
# ✅ ADMIN: Order Details
# -----------------------------
@app.get("/admin/order-details/{order_id}")
def get_order_details(order_id: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                p.name,
                p.image_url,
                oi.quantity
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        rows = cur.fetchall()

        return [
            {
                "product_name": row[0],
                "image": f"{BASE_URL}/uploads/{row[1]}" if row[1] else None,
                "quantity": row[2]
            }
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()