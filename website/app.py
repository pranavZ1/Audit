"""
Flask backend for the Audit Dashboard.
All data served from MongoDB Atlas (migrated from SQLite).
"""

from flask import Flask, jsonify, request, send_from_directory
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__, static_folder="static")

# ─── MongoDB connection (lazy singleton) ──────────────────────────────────────
_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI not set in .env")
        _client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        _db = _client["Audit"]
    return _db


def col_esw():
    return get_db()["eswathu"]


def col_panch():
    return get_db()["panchatantra"]


def col_mg():
    return get_db()["mgnrega"]


# ─── Serve frontend ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ─── ESWATHU APIs ─────────────────────────────────────────────────────────────
@app.route("/api/eswathu/districts")
def eswathu_districts():
    return jsonify(sorted(col_esw().distinct("district")))


@app.route("/api/eswathu/taluks")
def eswathu_taluks():
    district = request.args.get("district", "")
    return jsonify(sorted(col_esw().distinct("taluk", {"district": district})))


@app.route("/api/eswathu/gps")
def eswathu_gps():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    return jsonify(sorted(col_esw().distinct("gp", {"district": district, "taluk": taluk})))


@app.route("/api/eswathu/data")
def eswathu_data():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    limit = int(request.args.get("limit", 500))
    offset = int(request.args.get("offset", 0))
    flt = {"district": district, "taluk": taluk, "gp": gp}
    proj = {"_id": 0, "property_id": 1, "asset_number": 1,
            "property_classification": 1, "owners": 1, "form_type": 1}
    total = col_esw().count_documents(flt)
    rows = list(col_esw().find(flt, proj).skip(offset).limit(limit))
    return jsonify({"total": total, "data": rows})


# ─── PANCHATANTRA APIs ─────────────────────────────────────────
@app.route("/api/panchatantra/districts")
def panch_districts():
    return jsonify(sorted(col_panch().distinct("district")))


@app.route("/api/panchatantra/taluks")
def panch_taluks():
    district = request.args.get("district", "")
    return jsonify(sorted(col_panch().distinct("taluk", {"district": district})))


@app.route("/api/panchatantra/gps")
def panch_gps():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    return jsonify(sorted(col_panch().distinct("gp", {"district": district, "taluk": taluk})))


@app.route("/api/panchatantra/villages")
def panch_villages():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    return jsonify(sorted(col_panch().distinct(
        "village_code", {"district": district, "taluk": taluk, "gp": gp}
    )))


@app.route("/api/panchatantra/data")
def panch_data():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    village = request.args.get("village", "")
    limit = int(request.args.get("limit", 500))
    offset = int(request.args.get("offset", 0))
    flt = {"district": district, "taluk": taluk, "gp": gp}
    if village:
        flt["village_code"] = village
    proj = {"_id": 0, "property_id": 1, "property_number": 1,
            "property_owner_name": 1, "current_demand": 1, "arrears": 1,
            "total_demand": 1, "total_demand_collection": 1, "total_balance": 1,
            "discount": 1, "round_off": 1, "village_code": 1}
    total = col_panch().count_documents(flt)
    rows = list(col_panch().find(flt, proj).skip(offset).limit(limit))
    return jsonify({"total": total, "data": rows})


# ─── MATCH API ──────────────────────────────────────────────────
@app.route("/api/match")
def match_properties():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    limit = int(request.args.get("limit", 500))
    offset = int(request.args.get("offset", 0))
    flt = {"district": district, "taluk": taluk, "gp": gp}

    esw_docs = list(col_esw().find(flt, {
        "_id": 0, "property_id": 1, "asset_number": 1,
        "property_classification": 1, "owners": 1
    }))
    esw_map = {d["property_id"]: d for d in esw_docs}
    eswathu_total = len(esw_map)

    panch_docs = list(col_panch().find(flt, {
        "_id": 0, "property_id": 1, "property_number": 1, "property_owner_name": 1,
        "village_code": 1, "total_demand": 1, "total_balance": 1,
        "total_demand_collection": 1
    }))
    panch_total = len(set(p["property_id"] for p in panch_docs if p.get("property_id")))

    matched = []
    for p in panch_docs:
        pid = p.get("property_id")
        if pid and pid in esw_map:
            e = esw_map[pid]
            matched.append({
                "property_id": pid,
                "asset_number": e.get("asset_number"),
                "property_classification": e.get("property_classification"),
                "eswathu_owners": e.get("owners"),
                "property_number": p.get("property_number"),
                "panchatantra_owner": p.get("property_owner_name"),
                "village_code": p.get("village_code"),
                "total_demand": p.get("total_demand"),
                "total_balance": p.get("total_balance"),
                "total_demand_collection": p.get("total_demand_collection"),
            })

    matched.sort(key=lambda x: x["property_id"] or "")
    total_matched = len(matched)
    return jsonify({
        "total_matched": total_matched,
        "eswathu_total": eswathu_total,
        "panchatantra_total": panch_total,
        "data": matched[offset: offset + limit],
    })


# ─── MISSING PROPERTIES API ─────────────────────────────────────
@app.route("/api/match/missing")
def missing_properties():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    source = request.args.get("source", "eswathu")
    limit = int(request.args.get("limit", 500))
    offset = int(request.args.get("offset", 0))
    flt = {"district": district, "taluk": taluk, "gp": gp}

    if source == "eswathu":
        esw_docs = list(col_esw().find(flt, {
            "_id": 0, "property_id": 1, "asset_number": 1,
            "property_classification": 1, "owners": 1
        }))
        panch_ids = set(col_panch().distinct("property_id", flt))
        missing = [d for d in esw_docs if d.get("property_id") not in panch_ids]
    else:
        panch_docs = list(col_panch().find(flt, {
            "_id": 0, "property_id": 1, "property_number": 1,
            "property_owner_name": 1, "village_code": 1,
            "total_demand": 1, "total_balance": 1, "arrears": 1
        }))
        esw_ids = set(col_esw().distinct("property_id", flt))
        missing = [d for d in panch_docs if d.get("property_id") not in esw_ids]

    missing.sort(key=lambda x: x.get("property_id") or "")
    total = len(missing)
    return jsonify({"total": total, "source": source, "data": missing[offset: offset + limit]})


# ─── ANALYTICS API ──────────────────────────────────────────────
@app.route("/api/analytics/gp_summary")
def gp_summary():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    flt = {"district": district, "taluk": taluk, "gp": gp}

    village_raw = list(col_panch().aggregate([
        {"$match": flt},
        {"$group": {
            "_id": "$village_code",
            "total_properties": {"$sum": 1},
            "total_arrears": {"$sum": "$arrears"},
            "total_current_demand": {"$sum": "$current_demand"},
            "total_demand": {"$sum": "$total_demand"},
            "total_collection": {"$sum": "$total_demand_collection"},
            "total_balance": {"$sum": "$total_balance"},
            "avg_arrears": {"$avg": "$arrears"},
            "max_arrears": {"$max": "$arrears"},
            "defaulters_count": {"$sum": {"$cond": [{"$gt": ["$arrears", 0]}, 1, 0]}},
            "fully_paid_count": {"$sum": {"$cond": [{"$lte": ["$total_balance", 0]}, 1, 0]}},
        }},
        {"$sort": {"total_arrears": -1}},
    ]))
    village_stats = [{
        "village_code": r["_id"], "total_properties": r["total_properties"],
        "total_arrears": r["total_arrears"], "total_current_demand": r["total_current_demand"],
        "total_demand": r["total_demand"], "total_collection": r["total_collection"],
        "total_balance": r["total_balance"], "avg_arrears": r["avg_arrears"],
        "max_arrears": r["max_arrears"], "defaulters_count": r["defaulters_count"],
        "fully_paid_count": r["fully_paid_count"],
    } for r in village_raw]

    gp_raw = list(col_panch().aggregate([
        {"$match": flt},
        {"$group": {
            "_id": None,
            "total_properties": {"$sum": 1},
            "total_arrears": {"$sum": "$arrears"},
            "total_current_demand": {"$sum": "$current_demand"},
            "total_demand": {"$sum": "$total_demand"},
            "total_collection": {"$sum": "$total_demand_collection"},
            "total_balance": {"$sum": "$total_balance"},
            "avg_arrears": {"$avg": "$arrears"},
            "max_arrears": {"$max": "$arrears"},
            "defaulters_count": {"$sum": {"$cond": [{"$gt": ["$arrears", 0]}, 1, 0]}},
            "fully_paid_count": {"$sum": {"$cond": [{"$lte": ["$total_balance", 0]}, 1, 0]}},
        }},
    ]))
    gp_stats = gp_raw[0] if gp_raw else {}
    gp_stats.pop("_id", None)

    top_defaulters = list(col_panch().find(
        {**flt, "arrears": {"$gt": 0}},
        {"_id": 0, "property_id": 1, "property_owner_name": 1, "village_code": 1,
         "arrears": 1, "total_demand": 1, "total_balance": 1}
    ).sort("arrears", DESCENDING).limit(10))

    buckets_raw = list(col_panch().aggregate([
        {"$match": flt},
        {"$addFields": {"bucket": {"$switch": {"branches": [
            {"case": {"$lte": ["$arrears", 0]}, "then": "No Arrears"},
            {"case": {"$lte": ["$arrears", 500]}, "then": "₹1 - ₹500"},
            {"case": {"$lte": ["$arrears", 2000]}, "then": "₹501 - ₹2000"},
            {"case": {"$lte": ["$arrears", 5000]}, "then": "₹2001 - ₹5000"},
            {"case": {"$lte": ["$arrears", 10000]}, "then": "₹5001 - ₹10000"},
        ], "default": "₹10000+"}}}},
        {"$group": {"_id": "$bucket", "count": {"$sum": 1}, "total_arrears": {"$sum": "$arrears"}}},
    ]))
    buckets = [{"bucket": r["_id"], "count": r["count"], "total_arrears": r["total_arrears"]}
               for r in buckets_raw]

    total_demand = gp_stats.get("total_demand") or 0
    total_collection = gp_stats.get("total_collection") or 0
    collection_rate = round(total_collection / total_demand * 100, 1) if total_demand > 0 else 0

    return jsonify({
        "gp_summary": gp_stats,
        "village_breakdown": village_stats,
        "top_defaulters": top_defaulters,
        "arrears_distribution": buckets,
        "collection_rate": collection_rate,
    })


@app.route("/api/analytics/match_summary")
def match_summary():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    flt = {"district": district, "taluk": taluk, "gp": gp}

    esw_ids = set(col_esw().distinct("property_id", flt))
    panch_ids = set(col_panch().distinct("property_id", flt))
    matched_ids = esw_ids & panch_ids
    only_esw = esw_ids - panch_ids
    only_panch = panch_ids - esw_ids
    eswathu_count = len(esw_ids)
    matched_count = len(matched_ids)

    panch_docs = list(col_panch().find(flt, {
        "_id": 0, "property_id": 1, "arrears": 1, "total_demand": 1, "total_balance": 1
    }))
    unmatched = [p for p in panch_docs if p.get("property_id") not in esw_ids]
    unmatched_arrears = sum((p.get("arrears") or 0) for p in unmatched)
    unmatched_demand = sum((p.get("total_demand") or 0) for p in unmatched)
    unmatched_balance = sum((p.get("total_balance") or 0) for p in unmatched)

    return jsonify({
        "eswathu_total": eswathu_count,
        "matched": matched_count,
        "only_in_eswathu": len(only_esw),
        "only_in_panchatantra": len(only_panch),
        "match_rate": round(matched_count / eswathu_count * 100, 1) if eswathu_count > 0 else 0,
        "unmatched_financials": {
            "unmatched_arrears": unmatched_arrears,
            "unmatched_demand": unmatched_demand,
            "unmatched_balance": unmatched_balance,
        },
    })


# ─── MGNREGA APIs ─────────────────────────────────────────────
@app.route("/api/mgnrega/districts")
def mgnrega_districts():
    return jsonify(sorted(col_mg().distinct("district", {"is_total": "N"})))


@app.route("/api/mgnrega/years")
def mgnrega_years():
    return jsonify(sorted(col_mg().distinct("year")))


MG_PROJ = {
    "_id": 0, "block": 1, "panchayat": 1, "year": 1, "district": 1, "is_total": 1,
    "exp_unskilled_wage": 1, "exp_semiskilled_wage": 1,
    "exp_material": 1, "exp_tax": 1, "admin_exp_total": 1,
    "total_expenditure": 1, "total_availability": 1, "balance": 1,
    "payment_due_unskilled": 1, "payment_due_semiskilled": 1,
    "payment_due_material": 1, "payment_due_tax": 1, "payment_due_total": 1,
}


@app.route("/api/mgnrega/district_summary")
def mgnrega_district_summary():
    dist = request.args.get("district", "")
    year = request.args.get("year", "")
    q_total = {"is_total": "Y"}
    q_gp = {"is_total": "N"}
    if dist:
        q_total["district"] = dist
        q_gp["district"] = dist
    if year:
        q_total["year"] = year
        q_gp["year"] = year

    blocks_raw = list(col_mg().find(q_total, MG_PROJ).sort("block", ASCENDING))
    gp_count_map = {r["_id"]: r["gp_count"] for r in col_mg().aggregate([
        {"$match": q_gp}, {"$group": {"_id": "$block", "gp_count": {"$sum": 1}}}
    ])}
    gp_rows = list(col_mg().find(q_gp, {
        "_id": 0, "block": 1, "exp_unskilled_wage": 1,
        "exp_semiskilled_wage": 1, "total_expenditure": 1
    }))
    violation_map = {}
    for g in gp_rows:
        exp = g.get("total_expenditure") or 0
        wage = (g.get("exp_unskilled_wage") or 0) + (g.get("exp_semiskilled_wage") or 0)
        if exp > 0 and wage / exp * 100 < 60:
            blk = g.get("block")
            violation_map[blk] = violation_map.get(blk, 0) + 1

    block_data = []
    du = ds = dm = dt = dist_exp = dist_avail = total_gp_count = 0
    for b in blocks_raw:
        bexp = b.get("total_expenditure") or 0
        bwage = (b.get("exp_unskilled_wage") or 0) + (b.get("exp_semiskilled_wage") or 0)
        bmat = (b.get("exp_material") or 0) + (b.get("exp_tax") or 0)
        blk = b.get("block")
        gpc = gp_count_map.get(blk, 0)
        bd = {
            "block": blk,
            "total_unskilled": b.get("exp_unskilled_wage") or 0,
            "total_semiskilled": b.get("exp_semiskilled_wage") or 0,
            "total_material": b.get("exp_material") or 0,
            "total_tax": b.get("exp_tax") or 0,
            "total_admin": b.get("admin_exp_total") or 0,
            "total_expenditure": bexp,
            "total_availability": b.get("total_availability") or 0,
            "balance": b.get("balance") or 0,
            "wage_pct": round(bwage / bexp * 100, 2) if bexp > 0 else 0,
            "material_pct": round(bmat / bexp * 100, 2) if bexp > 0 else 0,
            "wage_amount": round(bwage, 2),
            "material_amount": round(bmat, 2),
            "compliant": (bwage / bexp * 100 >= 60) if bexp > 0 else True,
            "gp_count": gpc,
            "gp_violations": violation_map.get(blk, 0),
        }
        block_data.append(bd)
        du += b.get("exp_unskilled_wage") or 0
        ds += b.get("exp_semiskilled_wage") or 0
        dm += b.get("exp_material") or 0
        dt += b.get("exp_tax") or 0
        dist_exp += bexp
        dist_avail += b.get("total_availability") or 0
        total_gp_count += gpc

    wage_total = du + ds
    material_total = dm + dt
    wage_pct = round(wage_total / dist_exp * 100, 2) if dist_exp > 0 else 0
    material_pct = round(material_total / dist_exp * 100, 2) if dist_exp > 0 else 0
    return jsonify({
        "district": dist or "ALL",
        "total_expenditure": round(dist_exp, 2),
        "total_availability": round(dist_avail, 2),
        "wage_total": round(wage_total, 2),
        "material_total": round(material_total, 2),
        "wage_pct": wage_pct,
        "material_pct": material_pct,
        "compliant": wage_pct >= 60,
        "gp_count": total_gp_count,
        "blocks": block_data,
    })


@app.route("/api/mgnrega/block_detail")
def mgnrega_block_detail():
    block = request.args.get("block", "")
    year = request.args.get("year", "")
    q_gp = {"block": block, "is_total": "N"}
    q_total = {"block": block, "is_total": "Y"}
    if year:
        q_gp["year"] = year
        q_total["year"] = year

    gps_raw = list(col_mg().find(q_gp, MG_PROJ).sort("panchayat", ASCENDING))
    bt = col_mg().find_one(q_total, MG_PROJ)

    gp_data = []
    violators = 0
    for g in gps_raw:
        exp = g.get("total_expenditure") or 0
        wage = (g.get("exp_unskilled_wage") or 0) + (g.get("exp_semiskilled_wage") or 0)
        mat = (g.get("exp_material") or 0) + (g.get("exp_tax") or 0)
        compliant = (wage / exp * 100 >= 60) if exp > 0 else True
        if not compliant:
            violators += 1
        gp_data.append({
            "panchayat": g.get("panchayat"),
            "exp_unskilled_wage": g.get("exp_unskilled_wage") or 0,
            "exp_semiskilled_wage": g.get("exp_semiskilled_wage") or 0,
            "exp_material": g.get("exp_material") or 0,
            "exp_tax": g.get("exp_tax") or 0,
            "admin_exp_total": g.get("admin_exp_total") or 0,
            "total_expenditure": exp,
            "total_availability": g.get("total_availability") or 0,
            "balance": g.get("balance") or 0,
            "payment_due_unskilled": g.get("payment_due_unskilled") or 0,
            "payment_due_semiskilled": g.get("payment_due_semiskilled") or 0,
            "payment_due_material": g.get("payment_due_material") or 0,
            "payment_due_tax": g.get("payment_due_tax") or 0,
            "payment_due_total": g.get("payment_due_total") or 0,
            "wage_amount": round(wage, 2),
            "material_amount": round(mat, 2),
            "wage_pct": round(wage / exp * 100, 2) if exp > 0 else 0,
            "material_pct": round(mat / exp * 100, 2) if exp > 0 else 0,
            "compliant": compliant,
        })

    if bt:
        bt_exp = bt.get("total_expenditure") or 0
        bt_wage = (bt.get("exp_unskilled_wage") or 0) + (bt.get("exp_semiskilled_wage") or 0)
        bt_mat = (bt.get("exp_material") or 0) + (bt.get("exp_tax") or 0)
    else:
        bt_exp = sum(g["total_expenditure"] for g in gp_data)
        bt_wage = sum(g["wage_amount"] for g in gp_data)
        bt_mat = sum(g["material_amount"] for g in gp_data)

    return jsonify({
        "block": block,
        "total_gps": len(gp_data),
        "violators": violators,
        "compliant_count": len(gp_data) - violators,
        "block_wage_pct": round(bt_wage / bt_exp * 100, 2) if bt_exp > 0 else 0,
        "block_material_pct": round(bt_mat / bt_exp * 100, 2) if bt_exp > 0 else 0,
        "block_total_expenditure": round(bt_exp, 2),
        "gps": gp_data,
    })


@app.route("/api/mgnrega/balance_sheet")
def mgnrega_balance_sheet():
    dist = request.args.get("district", "")
    q_total = {"is_total": "Y"}
    q_gp = {"is_total": "N"}
    if dist:
        q_total["district"] = dist
        q_gp["district"] = dist

    year_raw = list(col_mg().aggregate([
        {"$match": q_total},
        {"$group": {
            "_id": "$year",
            "total_availability": {"$sum": "$total_availability"},
            "total_expenditure": {"$sum": "$total_expenditure"},
            "balance": {"$sum": "$balance"},
            "total_unskilled": {"$sum": "$exp_unskilled_wage"},
            "total_semiskilled": {"$sum": "$exp_semiskilled_wage"},
            "total_material": {"$sum": "$exp_material"},
            "total_tax": {"$sum": "$exp_tax"},
            "total_admin": {"$sum": "$admin_exp_total"},
            "total_pending": {"$sum": "$payment_due_total"},
        }},
        {"$sort": {"_id": 1}},
    ]))
    block_year_raw = list(col_mg().find(q_total, {
        "_id": 0, "year": 1, "block": 1,
        "total_availability": 1, "total_expenditure": 1, "balance": 1,
        "exp_unskilled_wage": 1, "exp_semiskilled_wage": 1,
        "exp_material": 1, "exp_tax": 1,
    }).sort([("year", ASCENDING), ("block", ASCENDING)]))
    gp_count_map = {r["_id"]: r["gp_count"] for r in col_mg().aggregate([
        {"$match": q_gp}, {"$group": {"_id": "$year", "gp_count": {"$sum": 1}}}
    ])}

    years = []
    prev = None
    for y in year_raw:
        total_exp = y.get("total_expenditure") or 0
        total_avail = y.get("total_availability") or 0
        wage = (y.get("total_unskilled") or 0) + (y.get("total_semiskilled") or 0)
        mat = (y.get("total_material") or 0) + (y.get("total_tax") or 0)
        util_pct = round(total_exp / total_avail * 100, 2) if total_avail > 0 else 0
        entry = {
            "year": y["_id"],
            "total_released": round(total_avail, 2),
            "total_utilisation": round(total_exp, 2),
            "balance": round(y.get("balance") or 0, 2),
            "utilisation_pct": util_pct,
            "wage_amount": round(wage, 2),
            "material_amount": round(mat, 2),
            "wage_pct": round(wage / total_exp * 100, 2) if total_exp > 0 else 0,
            "material_pct": round(mat / total_exp * 100, 2) if total_exp > 0 else 0,
            "admin_exp": round(y.get("total_admin") or 0, 2),
            "pending_payments": round(y.get("total_pending") or 0, 2),
            "gp_count": gp_count_map.get(y["_id"], 0),
            "yoy_released": None, "yoy_utilisation": None,
            "yoy_balance": None, "yoy_utilisation_pct": None,
        }
        if prev:
            entry["yoy_released"] = round(entry["total_released"] - prev["total_released"], 2)
            entry["yoy_utilisation"] = round(entry["total_utilisation"] - prev["total_utilisation"], 2)
            entry["yoy_balance"] = round(entry["balance"] - prev["balance"], 2)
            entry["yoy_utilisation_pct"] = round(entry["utilisation_pct"] - prev["utilisation_pct"], 2)
        prev = entry
        years.append(entry)

    blocks_by_year = {}
    for b in block_year_raw:
        yr = b.get("year")
        if yr not in blocks_by_year:
            blocks_by_year[yr] = []
        total_exp = b.get("total_expenditure") or 0
        total_avail = b.get("total_availability") or 0
        wage = (b.get("exp_unskilled_wage") or 0) + (b.get("exp_semiskilled_wage") or 0)
        mat = (b.get("exp_material") or 0) + (b.get("exp_tax") or 0)
        blocks_by_year[yr].append({
            "block": b.get("block"),
            "total_released": round(total_avail, 2),
            "total_utilisation": round(total_exp, 2),
            "balance": round(b.get("balance") or 0, 2),
            "utilisation_pct": round(total_exp / total_avail * 100, 2) if total_avail > 0 else 0,
            "wage_amount": round(wage, 2),
            "material_amount": round(mat, 2),
        })

    return jsonify({"district": dist or "ALL", "years": years, "blocks_by_year": blocks_by_year})


@app.route("/api/mgnrega/balance_sheet_block")
def mgnrega_balance_sheet_block():
    block = request.args.get("block", "")
    if not block:
        return jsonify({"error": "block parameter required"}), 400

    gps_raw = list(col_mg().find({"block": block, "is_total": "N"}, MG_PROJ)
                   .sort("panchayat", ASCENDING))
    bt = col_mg().find_one({"block": block, "is_total": "Y"}, MG_PROJ)

    gp_data = []
    for g in gps_raw:
        total_exp = g.get("total_expenditure") or 0
        total_avail = g.get("total_availability") or 0
        wage = (g.get("exp_unskilled_wage") or 0) + (g.get("exp_semiskilled_wage") or 0)
        mat = (g.get("exp_material") or 0) + (g.get("exp_tax") or 0)
        gp_data.append({
            "panchayat": g.get("panchayat"),
            "total_released": round(total_avail, 2),
            "total_utilisation": round(total_exp, 2),
            "balance": round(g.get("balance") or 0, 2),
            "utilisation_pct": round(total_exp / total_avail * 100, 2) if total_avail > 0 else 0,
            "wage_amount": round(wage, 2),
            "material_amount": round(mat, 2),
            "wage_pct": round(wage / total_exp * 100, 2) if total_exp > 0 else 0,
            "material_pct": round(mat / total_exp * 100, 2) if total_exp > 0 else 0,
            "admin_exp": round(g.get("admin_exp_total") or 0, 2),
            "pending_payments": round(g.get("payment_due_total") or 0, 2),
        })

    block_summary = {}
    if bt:
        bt_exp = bt.get("total_expenditure") or 0
        bt_avail = bt.get("total_availability") or 0
        bt_wage = (bt.get("exp_unskilled_wage") or 0) + (bt.get("exp_semiskilled_wage") or 0)
        bt_mat = (bt.get("exp_material") or 0) + (bt.get("exp_tax") or 0)
        block_summary = {
            "total_released": round(bt_avail, 2),
            "total_utilisation": round(bt_exp, 2),
            "balance": round(bt.get("balance") or 0, 2),
            "utilisation_pct": round(bt_exp / bt_avail * 100, 2) if bt_avail > 0 else 0,
            "wage_amount": round(bt_wage, 2),
            "material_amount": round(bt_mat, 2),
            "wage_pct": round(bt_wage / bt_exp * 100, 2) if bt_exp > 0 else 0,
            "material_pct": round(bt_mat / bt_exp * 100, 2) if bt_exp > 0 else 0,
            "admin_exp": round(bt.get("admin_exp_total") or 0, 2),
            "pending_payments": round(bt.get("payment_due_total") or 0, 2),
        }

    return jsonify({"block": block, "total_gps": len(gp_data),
                    "block_summary": block_summary, "gps": gp_data})


# ─── DEFAULTERS (PAGINATED) API ──────────────────────────────
@app.route("/api/analytics/defaulters")
def analytics_defaulters():
    district = request.args.get("district", "")
    taluk = request.args.get("taluk", "")
    gp = request.args.get("gp", "")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    flt = {"district": district, "taluk": taluk, "gp": gp, "arrears": {"$gt": 0}}
    proj = {"_id": 0, "property_id": 1, "property_number": 1, "property_owner_name": 1,
            "village_code": 1, "arrears": 1, "total_demand": 1,
            "total_demand_collection": 1, "total_balance": 1}
    total = col_panch().count_documents(flt)
    rows = list(col_panch().find(flt, proj)
                .sort("arrears", DESCENDING).skip(offset).limit(limit))
    return jsonify({"total": total, "data": rows})


if __name__ == "__main__":
    print("Starting Audit Dashboard — MongoDB backend")
    print("Server: http://localhost:5001")
    app.run(debug=True, port=5001)
