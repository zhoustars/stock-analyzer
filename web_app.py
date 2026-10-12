# -*- coding: utf-8 -*-
"""
股票分析 Web 应用
通过网页输入股票代码，展示分析结果。
"""

import json
import numpy as np
from flask import Flask, request, jsonify, render_template

from stock_analyzer import get_stock_data, calc_indicators, analyze, analyze_position, ADVICE_DESC, get_stock_name

app = Flask(__name__)


def to_native(obj):
    """递归将 numpy 类型转为 Python 原生类型，便于 JSON 序列化"""
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj]
    return obj


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip()

    if not code.isdigit() or len(code) != 6:
        return jsonify({"error": "请输入 6 位数字股票代码"}), 400

    try:
        df, data_source, err_msg = get_stock_data(code)
        ind = calc_indicators(df)
        result = analyze(code, ind)

        result["advice_desc"] = ADVICE_DESC[result["advice"]]
        result["symbol"] = code
        result["name"] = get_stock_name(code)
        result["data_source"] = data_source
        result["debug_error"] = err_msg

        # 持仓分析（可选：买入价）
        buy_price_raw = str(data.get("buy_price", "")).strip()
        if buy_price_raw:
            try:
                buy_price = float(buy_price_raw)
                if buy_price > 0:
                    result["position"] = analyze_position(
                        buy_price, result["price"], result["total_score"]
                    )
            except ValueError:
                pass

        native = to_native(result)
        import json as _json
        return app.response_class(
            response=_json.dumps(native, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return app.response_class(
            response=_json.dumps({"error": f"分析失败: {e}"}, ensure_ascii=False),
            status=500,
            mimetype='application/json'
        )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
