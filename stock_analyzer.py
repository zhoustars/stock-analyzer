# -*- coding: utf-8 -*-
"""
股票分析程序
输入任意 A 股代码，基于技术指标综合评分，给出投资建议：
  A. 全仓买入
  B. 逢低分批买入
  C. 持仓观望
  D. 减仓止损
"""

import sys
import random
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ============================================================
# 第一部分：数据获取
# ============================================================

def _sina_prefix(symbol: str) -> str:
    """根据股票代码前缀返回新浪市场标识"""
    if symbol.startswith(("60", "68", "9")):
        return "sh"
    elif symbol.startswith(("00", "30", "20")):
        return "sz"
    else:
        return "bj"


def get_stock_name(symbol: str) -> str:
    """通过新浪接口获取股票名称"""
    import requests
    prefix = _sina_prefix(symbol)
    try:
        url = f"https://hq.sinajs.cn/list={prefix}{symbol}"
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        text = r.text
        start = text.find('"') + 1
        name = text[start:].split(",")[0]
        return name if name else symbol
    except Exception:
        return symbol


def fetch_realtime_quote(symbol: str):
    """通过新浪实时行情接口获取当日行情。

    新浪日线接口有延迟（最新数据常滞后一个交易日），
    实时接口可补回当日缺失数据，避免把昨收价误当成最新价。

    返回 dict: {name, open, prev_close, price, high, low, volume, date} 或 None
    """
    import requests
    prefix = _sina_prefix(symbol)
    url = f"https://hq.sinajs.cn/list={prefix}{symbol}"
    r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
    # 新浪返回 GBK 编码，按需解码
    r.encoding = "gbk"
    text = r.text
    start = text.find('"') + 1
    end_q = text.find('"', start)
    content = text[start:end_q]
    if not content:
        return None
    p = content.split(",")
    # 0:名称 1:今开 2:昨收 3:当前价 4:最高 5:最低
    # 6:买1价 7:卖1价 8:成交量(股) 9:成交额 30:日期 31:时间
    if len(p) < 32 or not p[3]:
        return None
    return {
        "name": p[0],
        "open": float(p[1]),
        "prev_close": float(p[2]),
        "price": float(p[3]),
        "high": float(p[4]),
        "low": float(p[5]),
        "volume": int(float(p[8])),
        "date": p[30],  # "YYYY-MM-DD"
    }


def fetch_real_data(symbol: str, days: int = 300):
    """通过 akshare 获取真实 A 股日线数据（新浪数据源），并补充当日实时行情。

    新浪日线接口通常滞后一个交易日，导致程序把前一交易日的收盘价
    当成"最新收盘价"。这里在日线数据基础上，用新浪实时行情接口
    补回当日数据，保证最新价格为当日实时价。
    """
    import akshare as ak

    sina_symbol = _sina_prefix(symbol) + symbol

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=int(days * 1.6))).strftime("%Y%m%d")

    df = ak.stock_zh_a_daily(symbol=sina_symbol, start_date=start, end_date=end, adjust="qfq")
    df = df[["date", "open", "close", "high", "low", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 用实时接口补回当日数据
    try:
        rt = fetch_realtime_quote(symbol)
        if rt and rt.get("date"):
            today_str = datetime.now().strftime("%Y-%m-%d")
            rt_date = rt["date"]
            # 实时接口返回的日期 == 今天，说明今天是交易日，应补回当日数据
            if rt_date == today_str:
                today_row = pd.DataFrame([{
                    "date": pd.to_datetime(rt_date),
                    "open": rt["open"],
                    "close": rt["price"],   # 当日实时价作为收盘价
                    "high": rt["high"],
                    "low": rt["low"],
                    "volume": rt["volume"],
                }])
                # 若日线已含当日记录，先删除再用实时数据覆盖
                df = df[df["date"].dt.strftime("%Y-%m-%d") != today_str]
                df = pd.concat([df, today_row], ignore_index=True)
                df = df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        print(f"  [提示] 获取当日实时行情失败，使用日线最新数据: {e}")

    return df


def fetch_sim_data(symbol: str, days: int = 300):
    """生成模拟行情数据（网络不可用时使用）"""
    random.seed(int(symbol.lstrip("036").lstrip("0") or "1") + 2026)
    np.random.seed(int(symbol.lstrip("036").lstrip("0") or "1") + 2026)

    # 基准价
    base = random.uniform(8, 200)
    # 趋势：随机选上升/震荡/下降
    regime = random.choice(["up", "sideways", "down", "up"])
    trend_step = {"up": 0.0015, "sideways": 0.0002, "down": -0.0015}[regime]

    dates = pd.bdate_range(end=datetime.now(), periods=days)
    closes, opens, highs, lows, volumes = [], [], [], [], []
    price = base

    for i in range(days):
        noise = np.random.randn() * 0.025
        change = trend_step + noise
        price *= (1 + change)
        o = price * (1 + np.random.randn() * 0.005)
        c = price
        h = max(o, c) * (1 + abs(np.random.randn()) * 0.008)
        l = min(o, c) * (1 - abs(np.random.randn()) * 0.008)
        v = random.randint(500000, 20000000)
        opens.append(round(o, 2))
        closes.append(round(c, 2))
        highs.append(round(h, 2))
        lows.append(round(l, 2))
        volumes.append(v)
        price = c

    df = pd.DataFrame({
        "date": dates, "open": opens, "close": closes,
        "high": highs, "low": lows, "volume": volumes,
    })
    return df


def get_stock_data(symbol: str, days: int = 300):
    """获取股票数据：优先真实数据，失败则用模拟数据"""
    import os
    debug_info = os.environ.get("STOCK_DEBUG", "")
    try:
        df = fetch_real_data(symbol, days)
        if len(df) >= 30:
            return df, "实时数据 (akshare)", ""
    except Exception as e:
        err = str(e)
        print(f"  [提示] 实时数据获取失败: {err}")
        print(f"  [提示] 自动切换至模拟数据模式，分析结果仅供参考。")
        if debug_info:
            return fetch_sim_data(symbol, days), "模拟数据 (离线模式)", err
    return fetch_sim_data(symbol, days), "模拟数据 (离线模式)", ""


# ============================================================
# 第二部分：技术指标计算
# ============================================================

def calc_indicators(df: pd.DataFrame) -> dict:
    """计算各项技术指标"""
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    vol = df["volume"].values.astype(float)
    n = len(close)

    # --- 移动平均线 ---
    def ma(arr, p):
        out = np.full(len(arr), np.nan)
        for i in range(p - 1, len(arr)):
            out[i] = arr[i - p + 1: i + 1].mean()
        return out

    ma5 = ma(close, 5)
    ma10 = ma(close, 10)
    ma20 = ma(close, 20)
    ma60 = ma(close, 60)
    ma250 = ma(close, 250)

    # --- MACD ---
    def ema(arr, p):
        out = np.full(len(arr), np.nan)
        k = 2 / (p + 1)
        # 找到第一个连续 p 个非 NaN 的起始位置
        count = 0
        start = None
        for idx in range(len(arr)):
            if not np.isnan(arr[idx]):
                count += 1
                if count == p:
                    start = idx - p + 1
                    break
            else:
                count = 0
        if start is None:
            return out
        out[start + p - 1] = arr[start: start + p].mean()
        for idx in range(start + p, len(arr)):
            prev = out[idx - 1]
            cur = arr[idx]
            if not np.isnan(cur) and not np.isnan(prev):
                out[idx] = cur * k + prev * (1 - k)
            elif not np.isnan(prev):
                out[idx] = prev
        return out

    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)
    macd_bar = (dif - dea) * 2

    # --- RSI (14) ---
    def rsi(arr, p=14):
        out = np.full(len(arr), np.nan)
        diff = np.diff(arr)
        for i in range(p, len(arr)):
            seg = diff[i - p: i]
            gain = seg[seg > 0].mean() if np.any(seg > 0) else 0
            loss = -seg[seg < 0].mean() if np.any(seg < 0) else 0.0001
            rs = gain / loss
            out[i] = 100 - 100 / (1 + rs)
        return out

    rsi_val = rsi(close)

    # --- KDJ ---
    def kdj(h, l, c, p=9):
        k_arr = np.full(len(c), 50.0)
        d_arr = np.full(len(c), 50.0)
        for i in range(p - 1, len(c)):
            hh = h[i - p + 1: i + 1].max()
            ll = l[i - p + 1: i + 1].min()
            rsv = (c[i] - ll) / (hh - ll) * 100 if hh != ll else 50
            k_arr[i] = k_arr[i - 1] * 2 / 3 + rsv / 3
            d_arr[i] = d_arr[i - 1] * 2 / 3 + k_arr[i] / 3
        j_arr = 3 * k_arr - 2 * d_arr
        return k_arr, d_arr, j_arr

    k_val, d_val, j_val = kdj(high, low, close)

    # --- 布林带 (20, 2σ) ---
    def boll(arr, p=20):
        mid = np.full(len(arr), np.nan)
        up = np.full(len(arr), np.nan)
        lo = np.full(len(arr), np.nan)
        for i in range(p - 1, len(arr)):
            seg = arr[i - p + 1: i + 1]
            mid[i] = seg.mean()
            std = seg.std()
            up[i] = mid[i] + 2 * std
            lo[i] = mid[i] - 2 * std
        return mid, up, lo

    boll_mid, boll_up, boll_lo = boll(close)

    # --- 成交量均线 ---
    vol_ma5 = ma(vol, 5)
    vol_ma10 = ma(vol, 10)

    return {
        "close": close, "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "ma250": ma250,
        "dif": dif, "dea": dea, "macd_bar": macd_bar,
        "rsi": rsi_val,
        "k": k_val, "d": d_val, "j": j_val,
        "boll_mid": boll_mid, "boll_up": boll_up, "boll_lo": boll_lo,
        "vol": vol, "vol_ma5": vol_ma5, "vol_ma10": vol_ma10,
        "high": high, "low": low,
    }


# ============================================================
# 第三部分：综合评分与投资建议
# ============================================================

def analyze(symbol: str, ind: dict) -> dict:
    """根据技术指标综合评分，给出投资建议"""
    i = len(ind["close"]) - 1
    close = ind["close"]
    reasons = []

    # ========== 1. 趋势评分 (均线排列) ==========
    trend_score = 0
    price = close[i]

    # 均线多头排列
    if not np.isnan(ind["ma60"][i]):
        if ind["ma5"][i] > ind["ma10"][i] > ind["ma20"][i] > ind["ma60"][i]:
            trend_score = 25
            reasons.append("均线多头排列（MA5>MA10>MA20>MA60），强势上升趋势")
        elif ind["ma5"][i] > ind["ma10"][i] > ind["ma20"][i]:
            trend_score = 18
            reasons.append("短期均线多头排列，上升趋势")
        elif ind["ma5"][i] > ind["ma10"][i]:
            trend_score = 10
            reasons.append("MA5 上穿 MA10，短期走强")
        elif ind["ma5"][i] < ind["ma10"][i] < ind["ma20"][i] < ind["ma60"][i]:
            trend_score = -25
            reasons.append("均线空头排列（MA5<MA10<MA20<MA60），强势下降趋势")
        elif ind["ma5"][i] < ind["ma10"][i] < ind["ma20"][i]:
            trend_score = -18
            reasons.append("短期均线空头排列，下降趋势")
        elif ind["ma5"][i] < ind["ma10"][i]:
            trend_score = -10
            reasons.append("MA5 下穿 MA10，短期走弱")
        else:
            trend_score = 0
            reasons.append("均线交叉混乱，趋势不明")
    else:
        trend_score = 10 if ind["ma5"][i] > ind["ma10"][i] else -10

    # 价格与 MA20 关系
    if not np.isnan(ind["ma20"][i]):
        if price > ind["ma20"][i]:
            trend_score += 5
        else:
            trend_score -= 5

    # ========== 2. MACD 动量评分 ==========
    macd_score = 0
    dif_val = ind["dif"][i]
    dea_val = ind["dea"][i]
    macd_bar = ind["macd_bar"][i]

    if not np.isnan(dif_val) and not np.isnan(dea_val):
        if dif_val > dea_val and dif_val > 0:
            macd_score = 20
            reasons.append("MACD 金叉且 DIF>0，多头动能强劲")
        elif dif_val > dea_val:
            macd_score = 12
            reasons.append("MACD 金叉，动能转多")
        elif dif_val < dea_val and dif_val < 0:
            macd_score = -20
            reasons.append("MACD 死叉且 DIF<0，空头动能强劲")
        elif dif_val < dea_val:
            macd_score = -12
            reasons.append("MACD 死叉，动能转空")
        else:
            macd_score = 0

        # MACD 柱变化
        if i >= 1 and macd_bar > ind["macd_bar"][i - 1]:
            macd_score += 3
        else:
            macd_score -= 3

    # ========== 3. RSI 评分 ==========
    rsi_score = 0
    rsi_val = ind["rsi"][i]
    if not np.isnan(rsi_val):
        if rsi_val > 80:
            rsi_score = -10
            reasons.append(f"RSI={rsi_val:.1f}，超买，存在回调风险")
        elif rsi_val > 65:
            rsi_score = 8
            reasons.append(f"RSI={rsi_val:.1f}，偏强")
        elif 40 <= rsi_val <= 65:
            rsi_score = 12
            reasons.append(f"RSI={rsi_val:.1f}，健康多头区间")
        elif 30 <= rsi_val < 40:
            rsi_score = -2
            reasons.append(f"RSI={rsi_val:.1f}，偏弱")
        else:
            rsi_score = 5
            reasons.append(f"RSI={rsi_val:.1f}，超卖，可能反弹")

    # ========== 4. KDJ 评分 ==========
    kdj_score = 0
    k_v, d_v, j_v = ind["k"][i], ind["d"][i], ind["j"][i]
    if not np.isnan(k_v):
        if k_v > d_v and j_v > k_v:
            kdj_score = 12
            reasons.append(f"KDJ 金叉且 J>K>D（K={k_v:.1f}, D={d_v:.1f}, J={j_v:.1f}）")
        elif k_v > d_v:
            kdj_score = 6
            reasons.append(f"KDJ 金叉（K={k_v:.1f}, D={d_v:.1f}）")
        elif k_v < d_v and j_v < k_v:
            kdj_score = -12
            reasons.append(f"KDJ 死叉且 J<K<D（K={k_v:.1f}, D={d_v:.1f}, J={j_v:.1f}）")
        elif k_v < d_v:
            kdj_score = -6
            reasons.append(f"KDJ 死叉（K={k_v:.1f}, D={d_v:.1f}）")

        if j_v > 100:
            kdj_score -= 5
        elif j_v < 0:
            kdj_score += 3

    # ========== 5. 布林带位置评分 ==========
    boll_score = 0
    if not np.isnan(ind["boll_up"][i]):
        boll_pct = (price - ind["boll_lo"][i]) / (ind["boll_up"][i] - ind["boll_lo"][i])
        if boll_pct > 0.85:
            boll_score = -8
            reasons.append(f"股价触及布林带上轨（位置{boll_pct*100:.0f}%），高位风险")
        elif boll_pct > 0.5:
            boll_score = 5
            reasons.append(f"股价处于布林带中上区间（位置{boll_pct*100:.0f}%）")
        elif boll_pct > 0.15:
            boll_score = 3
            reasons.append(f"股价处于布林带中下区间（位置{boll_pct*100:.0f}%）")
        else:
            boll_score = 6
            reasons.append(f"股价触及布林带下轨（位置{boll_pct*100:.0f}%），可能超跌反弹")

    # ========== 6. 成交量评分 ==========
    vol_score = 0
    if not np.isnan(ind["vol_ma5"][i]):
        vol_ratio = ind["vol"][i] / ind["vol_ma5"][i] if ind["vol_ma5"][i] > 0 else 1
        if vol_ratio > 2.0:
            vol_score = 8
            reasons.append(f"放量明显（量比{vol_ratio:.1f}），资金活跃")
        elif vol_ratio > 1.5:
            vol_score = 5
            reasons.append(f"温和放量（量比{vol_ratio:.1f}）")
        elif vol_ratio > 0.7:
            vol_score = 2
            reasons.append(f"成交量正常（量比{vol_ratio:.1f}）")
        else:
            vol_score = -3
            reasons.append(f"缩量明显（量比{vol_ratio:.1f}），动能不足")

    # ========== 7. 近期涨跌幅 ==========
    chg_score = 0
    if i >= 5:
        pct5 = (close[i] / close[i - 5] - 1) * 100
        if pct5 > 15:
            chg_score = -5
            reasons.append(f"近5日涨幅{pct5:.1f}%，短期涨幅过大")
        elif pct5 > 3:
            chg_score = 5
            reasons.append(f"近5日涨幅{pct5:.1f}%，走势稳健")
        elif pct5 > -3:
            chg_score = 0
            reasons.append(f"近5日涨跌{pct5:.1f}%，横盘整理")
        elif pct5 > -10:
            chg_score = -3
            reasons.append(f"近5日跌幅{pct5:.1f}%，短期走弱")
        else:
            chg_score = -8
            reasons.append(f"近5日跌幅{pct5:.1f}%，急跌风险")

    # ========== 8. 年线 (MA250) 评分 ==========
    year_score = 0
    if not np.isnan(ind["ma250"][i]):
        ma250_val = ind["ma250"][i]
        deviation = (price - ma250_val) / ma250_val * 100  # 偏离年线百分比

        if price > ma250_val:
            if deviation > 10:
                year_score = 15
                reasons.append(f"股价在年线上方{deviation:.1f}%，中长期多头格局")
            elif deviation > 3:
                year_score = 10
                reasons.append(f"股价在年线上方{deviation:.1f}%，中长期偏多")
            else:
                year_score = 6
                reasons.append(f"股价在年线附近（上方{deviation:.1f}%），多空争夺")
        else:
            if deviation < -10:
                year_score = -15
                reasons.append(f"股价在年线下方{deviation:.1f}%，中长期空头格局")
            elif deviation < -3:
                year_score = -10
                reasons.append(f"股价在年线下方{deviation:.1f}%，中长期偏空")
            else:
                year_score = -6
                reasons.append(f"股价在年线附近（下方{deviation:.1f}%），多空争夺")

        # 年线方向（5日前比较）
        if i >= 5 and not np.isnan(ind["ma250"][i - 5]):
            if ind["ma250"][i] > ind["ma250"][i - 5]:
                year_score += 3
            else:
                year_score -= 3
    else:
        reasons.append("年线数据不足（上市不满一年），暂不纳入评分")

    # ========== 综合评分 ==========
    total = trend_score + macd_score + rsi_score + kdj_score + boll_score + vol_score + chg_score + year_score

    # ========== 决策 ==========
    if total >= 45:
        advice = "A"
        action = "全仓买入"
    elif total >= 12:
        advice = "B"
        action = "逢低分批买入"
    elif total >= -18:
        advice = "C"
        action = "持仓观望"
    else:
        advice = "D"
        action = "减仓止损"

    scores = {
        "趋势": trend_score, "MACD": macd_score, "RSI": rsi_score,
        "KDJ": kdj_score, "布林带": boll_score, "成交量": vol_score, "涨跌幅": chg_score,
        "年线": year_score,
    }

    return {
        "advice": advice,
        "action": action,
        "total_score": total,
        "scores": scores,
        "reasons": reasons,
        "price": price,
        "indicators": {
            "RSI": rsi_val if not np.isnan(rsi_val) else 0,
            "MACD_DIF": dif_val if not np.isnan(dif_val) else 0,
            "MACD_DEA": dea_val if not np.isnan(dea_val) else 0,
            "KDJ_K": k_v if not np.isnan(k_v) else 0,
            "KDJ_D": d_v if not np.isnan(d_v) else 0,
            "KDJ_J": j_v if not np.isnan(j_v) else 0,
            "MA5": ind["ma5"][i] if not np.isnan(ind["ma5"][i]) else 0,
            "MA10": ind["ma10"][i] if not np.isnan(ind["ma10"][i]) else 0,
            "MA20": ind["ma20"][i] if not np.isnan(ind["ma20"][i]) else 0,
            "MA60": ind["ma60"][i] if not np.isnan(ind["ma60"][i]) else 0,
            "MA250": ind["ma250"][i] if not np.isnan(ind["ma250"][i]) else 0,
        },
    }


# ============================================================
# 第三部分B：持仓分析（买入价 vs 当前价）
# ============================================================

def analyze_position(buy_price: float, current_price: float, total_score: float) -> dict:
    """根据买入价和当前行情，给出持仓建议：割肉离场 / 持仓等解套 / 等"""
    buy_price = float(buy_price)
    current_price = float(current_price)
    total_score = float(total_score)
    pnl_pct = (current_price - buy_price) / buy_price * 100
    is_profit = pnl_pct >= 0

    if is_profit:
        if pnl_pct > 20:
            advice = "获利了结"
            detail = f"已盈利 {pnl_pct:.1f}%，涨幅较大，建议分批获利了结，锁定收益。"
        elif pnl_pct > 5:
            advice = "持有待涨"
            detail = f"已盈利 {pnl_pct:.1f}%，趋势良好，可继续持有，设好止盈位。"
        else:
            advice = "持有观察"
            detail = f"微盈 {pnl_pct:.1f}%，继续观察，突破可加仓。"
    else:
        loss_pct = -pnl_pct
        if loss_pct > 15:
            advice = "割肉离场"
            if total_score < -18:
                detail = f"已亏损 {loss_pct:.1f}%，且技术指标全面走空，建议果断割肉离场，避免更大损失。"
            else:
                detail = f"已亏损 {loss_pct:.1f}%，亏损较大，建议止损离场，等待更好时机重新入场。"
        elif loss_pct > 8:
            if total_score < -18:
                advice = "割肉离场"
                detail = f"已亏损 {loss_pct:.1f}%，技术指标偏空，趋势未现好转，建议止损离场。"
            else:
                advice = "减仓观望"
                detail = f"已亏损 {loss_pct:.1f}%，建议减半仓控制风险，余仓观望待变。"
        elif loss_pct > 3:
            if total_score < -18:
                advice = "减仓止损"
                detail = f"已亏损 {loss_pct:.1f}%，技术面走弱，建议减仓止损，防止亏损扩大。"
            else:
                advice = "持仓观望"
                detail = f"小幅亏损 {loss_pct:.1f}%，技术面尚可，建议持仓等解套，关注支撑位。"
        else:
            advice = "持仓等解套"
            detail = f"微亏 {loss_pct:.1f}%，跌幅不大，建议持仓等待反弹解套。"

    return {
        "buy_price": float(round(buy_price, 2)),
        "current_price": float(round(current_price, 2)),
        "pnl_pct": float(round(pnl_pct, 2)),
        "is_profit": bool(is_profit),
        "position_advice": str(advice),
        "position_detail": str(detail),
    }


# ============================================================
# 第四部分：输出报告
# ============================================================

ADVICE_DESC = {
    "A": "A. 全仓买入\n"
         "  综合评分显著为正，多项指标共振看多，趋势与动能强劲，\n"
         "  适合积极建仓。注意设好止盈位，分批获利了结。",
    "B": "B. 逢低分批买入\n"
         "  整体偏多但短期或有波动，建议逢回调分批低吸，\n"
         "  控制仓位在 3-5 成，待趋势确认后加仓。",
    "C": "C. 持仓观望\n"
         "  多空信号交织，趋势不明朗。建议保持现有仓位，\n"
         "  等待方向选择后再做决策。空仓者不宜追涨。",
    "D": "D. 减仓止损\n"
         "  综合评分为负，趋势走坏，多项指标看空。\n"
         "  建议及时减仓控制风险，破位个股果断止损离场。",
}


def print_report(symbol: str, data_source: str, result: dict):
    """打印分析报告"""
    ind = result["indicators"]
    bar = "═" * 58

    print(f"\n{bar}")
    name = result.get("name", symbol)
    print(f"  股票分析报告  |  {name}({symbol})  |  数据: {data_source}")
    print(bar)

    print(f"\n  最新收盘价: ¥{result['price']:.2f}")
    print(f"  MA5={ind['MA5']:.2f}  MA10={ind['MA10']:.2f}  "
          f"MA20={ind['MA20']:.2f}  MA60={ind['MA60']:.2f}  MA250={ind['MA250']:.2f}")
    print(f"  RSI(14)={ind['RSI']:.1f}")
    print(f"  MACD: DIF={ind['MACD_DIF']:.4f}  DEA={ind['MACD_DEA']:.4f}")
    print(f"  KDJ:  K={ind['KDJ_K']:.1f}  D={ind['KDJ_D']:.1f}  J={ind['KDJ_J']:.1f}")

    print(f"\n  {'─' * 52}")
    print(f"  各维度评分:")
    for name, score in result["scores"].items():
        sign = "+" if score >= 0 else ""
        bar_len = int(abs(score))
        bar_str = "█" * bar_len if score >= 0 else "▒" * bar_len
        print(f"    {name:<6} {sign}{score:>3}  {bar_str}")
    print(f"  {'─' * 52}")
    sign = "+" if result["total_score"] >= 0 else ""
    print(f"  综合评分:  {sign}{result['total_score']:.1f}  (范围约 -115 ~ +115)")
    print(f"  {'─' * 52}")

    print(f"\n  分析依据:")
    for r in result["reasons"]:
        print(f"    • {r}")

    print(f"\n  {'━' * 52}")
    print(f"  投资建议:")
    print(f"  {ADVICE_DESC[result['advice']]}")
    print(f"  {'━' * 52}")

    print(f"\n  ⚠ 风险提示: 本程序基于技术指标量化分析，仅供参考，\n"
          f"    不构成投资建议。股市有风险，投资需谨慎。\n")


# ============================================================
# 第五部分：主程序
# ============================================================

def analyze_one(symbol: str):
    """分析单只股票并打印报告"""
    print(f"\n  正在分析 {symbol} ...")
    try:
        df, data_source, _ = get_stock_data(symbol)
        ind = calc_indicators(df)
        result = analyze(symbol, ind)
        result["name"] = get_stock_name(symbol)
        print_report(symbol, data_source, result)
    except Exception as e:
        print(f"  ❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="A 股技术分析程序")
    parser.add_argument("codes", nargs="*", help="股票代码（可传多个），不传则进入交互模式")
    args = parser.parse_args()

    # 命令行直接传入股票代码 → 非交互模式，分析完即退出
    if args.codes:
        print("=" * 58)
        print("          📈  A 股技术分析程序  📈")
        print("=" * 58)
        for code in args.codes:
            if code.isdigit() and len(code) == 6:
                analyze_one(code)
            else:
                print(f"\n  ⚠ {code} 不是有效的 6 位股票代码，已跳过")
        return

    # 无参数 → 交互模式
    print("=" * 58)
    print("          📈  A 股技术分析程序  📈")
    print("=" * 58)
    print("  输入股票代码（如 600519、000001、300750），")
    print("  程序将给出投资建议。输入 q 退出。")
    print()

    while True:
        try:
            symbol = input("请输入股票代码 > ").strip()
        except EOFError:
            print("已退出。")
            break
        if symbol.lower() in ("q", "quit", "exit"):
            print("已退出。")
            break
        if not symbol.isdigit() or len(symbol) != 6:
            print("  ⚠ 请输入 6 位数字股票代码（如 600519）")
            continue
        analyze_one(symbol)


if __name__ == "__main__":
    main()
