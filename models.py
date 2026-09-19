import json
from pydantic import BaseModel, field_validator


class Receipt(BaseModel):
    date: str
    merchant: str
    total: float
    currency: str = "EUR"
    category: str
    payment_method: str
    raw_json: str = ""

    @field_validator("total")
    @classmethod
    def round_total(cls, v: float) -> float:
        return round(v, 2)


class Transaction(BaseModel):
    date: str
    description: str
    merchant: str
    amount: float
    type: str
    category: str
    statement_month: str

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: float) -> float:
        return round(v, 2)


class BankStatement(BaseModel):
    period: dict
    transactions: list[Transaction]


class Payslip(BaseModel):
    year: int
    month: int
    gross_total: float | None = None
    net_pay: float | None = None
    payout: float | None = None
    income_tax: float | None = None
    social_security_total: float | None = None
    employer: str | None = None
    gross_ytd: float | None = None
    tax_ytd: float | None = None
    raw_json: str = ""

    @field_validator("gross_total", "net_pay", "payout", "income_tax",
                     "social_security_total", "gross_ytd", "tax_ytd",
                     mode="before")
    @classmethod
    def round_money(cls, v: float | None) -> float | None:
        return round(v, 2) if v is not None else None
