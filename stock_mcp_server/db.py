"""SQLAlchemy models and queries for the Stock MCP — read-only."""

import os
from sqlalchemy import create_engine, Column, BigInteger, Integer, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    pass


class Branch(Base):
    __tablename__ = "branches"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(BigInteger, primary_key=True)
    branch_id = Column(BigInteger, ForeignKey("branches.id"), nullable=False)
    external_product_id = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    branch = relationship("Branch")



_engine = None


def get_session():
    global _engine
    if _engine is None:
        url = os.environ["STOCK_MCP_DATABASE_URL"]
        _engine = create_engine(url)
    return Session(_engine)



def list_branch_stock(branch_id):
    session = get_session()
    branch = session.get(Branch, branch_id)
    if not branch:
        return None
    items = (
        session.query(Stock)
        .filter(Stock.branch_id == branch_id, Stock.quantity > 0)
        .all()
    )
    return {
        "branch": {"branch_id": branch.id, "branch_name": branch.name},
        "items": [{"external_product_id": s.external_product_id, "quantity": s.quantity} for s in items],
    }


def get_stock_for_product(product_id):
    session = get_session()
    rows = session.query(Stock).filter(Stock.external_product_id == product_id).all()
    return {
        "external_product_id": product_id,
        "branches": [
            {"branch_id": r.branch_id, "branch_name": r.branch.name, "available_quantity": r.quantity}
            for r in rows
        ],
    }


def find_branches_with_stock(product_id, quantity):
    session = get_session()
    rows = (
        session.query(Stock)
        .filter(Stock.external_product_id == product_id, Stock.quantity >= quantity)
        .order_by(Stock.quantity.desc())
        .all()
    )
    return {
        "external_product_id": product_id,
        "requested_quantity": quantity,
        "branches": [
            {"branch_id": r.branch_id, "branch_name": r.branch.name, "available_quantity": r.quantity}
            for r in rows
        ],
    }


def find_branches_for_shopping_list(items):
    session = get_session()

    product_ids = [it["external_product_id"] for it in items]
    all_stock = session.query(Stock).filter(Stock.external_product_id.in_(product_ids)).all()


    branch_stock = {}
    branch_names = {}
    for s in all_stock:
        if s.branch_id not in branch_stock:
            branch_stock[s.branch_id] = {}
            branch_names[s.branch_id] = s.branch.name
        branch_stock[s.branch_id][s.external_product_id] = s.quantity


    for bid, stock in branch_stock.items():
        if all(stock.get(it["external_product_id"], 0) >= it["quantity"] for it in items):
            return {
                "complete": True,
                "strategy": "single_branch",
                "visits": [build_visit(bid, branch_names[bid], stock, items)],
                "missing_items": [],
            }


    missing = []
    for it in items:
        total = sum(s.quantity for s in all_stock if s.external_product_id == it["external_product_id"])
        if total < it["quantity"]:
            missing.append({"external_product_id": it["external_product_id"], "missing_quantity": it["quantity"] - total})

    if missing:
        return {"complete": False, "strategy": "unavailable", "visits": [], "missing_items": missing}


    visits = []
    for bid, stock in branch_stock.items():
        relevant = {it["external_product_id"]: stock.get(it["external_product_id"], 0) for it in items}
        if any(v > 0 for v in relevant.values()):
            visits.append({
                "branch_id": bid,
                "branch_name": branch_names[bid],
                "items": [
                    {"external_product_id": pid, "requested_quantity": next(it["quantity"] for it in items if it["external_product_id"] == pid), "available_quantity": qty}
                    for pid, qty in relevant.items()
                ],
            })

    return {"complete": True, "strategy": "multi_branch", "visits": visits, "missing_items": []}


def build_visit(bid, name, stock, items):
    return {
        "branch_id": bid,
        "branch_name": name,
        "items": [
            {"external_product_id": it["external_product_id"], "requested_quantity": it["quantity"], "available_quantity": stock.get(it["external_product_id"], 0)}
            for it in items
        ],
    }
