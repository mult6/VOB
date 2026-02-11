"""
Database models and configuration for the Telegram bot
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, BigInteger, Integer, SmallInteger, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


class Order(Base):
    """
    Orders table for tracking user orders
    """
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)  # Telegram user ID
    status = Column(SmallInteger, nullable=False, default=0)  # 0 or 1
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Order(id={self.id}, user_id={self.user_id}, status={self.status})>"


def init_database():
    """
    Initialize database - create all tables
    """
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully")


def get_session():
    """
    Get database session
    """
    return SessionLocal()


# Helper functions for order management
def create_order(user_id: int, status: int = 0):
    """
    Create a new order
    """
    session = get_session()
    try:
        order = Order(user_id=user_id, status=status)
        session.add(order)
        session.commit()
        session.refresh(order)
        return order
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_order_by_id(order_id: int):
    """
    Get order by ID
    """
    session = get_session()
    try:
        return session.query(Order).filter(Order.id == order_id).first()
    finally:
        session.close()


def get_orders_by_user(user_id: int):
    """
    Get all orders for a specific user
    """
    session = get_session()
    try:
        return session.query(Order).filter(Order.user_id == user_id).all()
    finally:
        session.close()


def update_order_status(order_id: int, status: int):
    """
    Update order status
    """
    session = get_session()
    try:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = status
            order.updated_at = datetime.utcnow()
            session.commit()
            return order
        return None
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_orders_by_status(status: int):
    """
    Get all orders with a specific status
    """
    session = get_session()
    try:
        return session.query(Order).filter(Order.status == status).all()
    finally:
        session.close()


def delete_order(order_id: int):
    """
    Delete an order
    """
    session = get_session()
    try:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order:
            session.delete(order)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()