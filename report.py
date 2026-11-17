#!/usr/bin/env python3
"""Отчёт по авансам: сколько выплачено и сколько осталось по каждой работе.

Запуск:
    python report.py --data data --date 2026-11-10 --out-dir out

Деньги считаются в копейках (Decimal), без float.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

KOPECK = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: str) -> Decimal:
    return Decimal(value.strip() or "0").quantize(KOPECK, rounding=ROUND_HALF_UP)


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt(value: Decimal) -> str:
    return f"{value.quantize(KOPECK):.2f}"


@dataclass
class Contract:
    contract_id: str
    contractor: str
    amount: Decimal
    signed_at: date


@dataclass
class Work:
    work_id: str
    contract_id: str
    title: str
    price: Decimal
    status_raw: str
    completed_at: date | None
    cancelled_at: date | None
    status: str = ""
    due: Decimal = field(default_factory=lambda: ZERO)
    paid_direct: Decimal = field(default_factory=lambda: ZERO)
    paid_advance: Decimal = field(default_factory=lambda: ZERO)

    @property
    def paid(self) -> Decimal:
        return self.paid_direct + self.paid_advance

    @property
    def left(self) -> Decimal:
        return self.due - self.paid


@dataclass
class Payment:
    payment_id: str
    contract_id: str
    work_id: str
    purpose: str
    amount: Decimal
    status: str
    created_at: date | None
    paid_at: date | None
    refunded_at: date | None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load(data: Path) -> tuple[list[Contract], list[Work], list[Payment]]:
    contracts = [
        Contract(r["contract_id"], r["contractor"], money(r["amount"]), parse_date(r["signed_at"]))
        for r in read_csv(data / "contracts.csv")
    ]
    works = [
        Work(
            r["work_id"],
            r["contract_id"],
            r["title"],
            money(r["price"]),
            r["status"],
            parse_date(r["completed_at"]),
            parse_date(r["cancelled_at"]),
        )
        for r in read_csv(data / "works.csv")
    ]
    payments = [
        Payment(
            r["payment_id"],
            r["contract_id"],
            (r.get("work_id") or "").strip(),
            r["purpose"],
            money(r["amount"]),
            r["status"],
            parse_date(r["created_at"]),
            parse_date(r["paid_at"]),
            parse_date(r["refunded_at"]),
        )
        for r in read_csv(data / "payments.csv")
    ]
    return contracts, works, payments


def status_as_of(work: Work, on: date) -> str:
    if work.cancelled_at and work.cancelled_at <= on:
        return "cancelled"
    if work.completed_at and work.completed_at <= on:
        return "done"
    return "planned"


def money_out(payment: Payment, on: date) -> bool:
    """Деньги у подрядчика на дату отчёта: ушли и ещё не возвращены."""
    if payment.paid_at is None or payment.paid_at > on:
        return False
    if payment.status == "refunded" and payment.refunded_at and payment.refunded_at <= on:
        return False
    if payment.status == "queued":
        return False
    return payment.status in {"paid", "refunded"}


def build(data: Path, on: date) -> tuple[list[Contract], list[Work], list[Payment], dict]:
    contracts, works, payments = load(data)
    by_contract: dict[str, list[Work]] = {c.contract_id: [] for c in contracts}
    for work in works:
        work.status = status_as_of(work, on)
        work.due = ZERO if work.status == "cancelled" else work.price
        by_contract.setdefault(work.contract_id, []).append(work)
    work_by_id = {w.work_id: w for w in works}

    totals: dict[str, dict] = {
        c.contract_id: {
            "paid": ZERO,
            "queued": ZERO,
            "refunded": ZERO,
            "unallocated": ZERO,
        }
        for c in contracts
    }

    for payment in payments:
        bucket = totals.setdefault(
            payment.contract_id,
            {"paid": ZERO, "queued": ZERO, "refunded": ZERO, "unallocated": ZERO},
        )
        if payment.status == "queued" and (payment.created_at is None or payment.created_at <= on):
            if payment.paid_at is None or payment.paid_at > on:
                bucket["queued"] += payment.amount
        if (
            payment.status == "refunded"
            and payment.refunded_at
            and payment.refunded_at <= on
            and payment.paid_at
            and payment.paid_at <= on
        ):
            bucket["refunded"] += payment.amount
        if not money_out(payment, on):
            continue
        bucket["paid"] += payment.amount
        if payment.work_id:
            work = work_by_id.get(payment.work_id)
            if work is None or work.contract_id != payment.contract_id:
                raise SystemExit(
                    f"{payment.payment_id}: работа {payment.work_id} не найдена в договоре {payment.contract_id}"
                )
            work.paid_direct += payment.amount
        else:
            bucket["unallocated"] += payment.amount

    for contract_id, contract_works in by_contract.items():
        pool = totals[contract_id]["unallocated"]
        done = sorted(
            (w for w in contract_works if w.status == "done"),
            key=lambda w: (w.completed_at, w.work_id),
        )
        for work in done:
            room = work.due - work.paid
            if room <= ZERO or pool <= ZERO:
                continue
            take = min(room, pool)
            work.paid_advance += take
            pool -= take
        totals[contract_id]["unallocated"] = pool

    return contracts, works, payments, totals


def write_reports(out: Path, on: date, contracts: list[Contract], works: list[Work], totals: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    works_path = out / "works.csv"
    contracts_path = out / "contracts.csv"
    with works_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            [
                "договор",
                "работа",
                "название",
                "статус на дату",
                "цена",
                "к оплате",
                "выплачено целевым",
                "выплачено из аванса",
                "выплачено всего",
                "осталось",
            ]
        )
        for work in works:
            writer.writerow(
                [
                    work.contract_id,
                    work.work_id,
                    work.title,
                    work.status,
                    fmt(work.price),
                    fmt(work.due),
                    fmt(work.paid_direct),
                    fmt(work.paid_advance),
                    fmt(work.paid),
                    fmt(work.left),
                ]
            )
    with contracts_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            [
                "договор",
                "подрядчик",
                "сумма договора",
                "к оплате по работам",
                "выплачено",
                "возвращено",
                "в очереди",
                "аванс не закрыт работами",
                "осталось доплатить",
            ]
        )
        by_id = {c.contract_id: c for c in contracts}
        for contract_id, contract in by_id.items():
            rows = [w for w in works if w.contract_id == contract_id]
            due = sum((w.due for w in rows), ZERO)
            paid = totals[contract_id]["paid"]
            writer.writerow(
                [
                    contract_id,
                    contract.contractor,
                    fmt(contract.amount),
                    fmt(due),
                    fmt(paid),
                    fmt(totals[contract_id]["refunded"]),
                    fmt(totals[contract_id]["queued"]),
                    fmt(totals[contract_id]["unallocated"]),
                    fmt(due - paid),
                ]
            )
    print(f"дата отчёта: {on.isoformat()}")
    print(f"работы: {works_path}")
    print(f"договоры: {contracts_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Отчёт: выплачено и остаток по работам договора")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--date", type=parse_date, default=date(2026, 11, 10))
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    args = parser.parse_args(argv)
    if args.date is None:
        parser.error("нужна дата ГГГГ-ММ-ДД")
    contracts, works, _payments, totals = build(args.data, args.date)
    write_reports(args.out_dir, args.date, contracts, works, totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
