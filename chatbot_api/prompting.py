"""Dựng prompt gửi cho model. Đây là NƠI DUY NHẤT quyết định định dạng prompt.

Khi thay bằng model fine-tune: nếu model được train theo định dạng prompt khác,
chỉ cần sửa build_messages() ở đây, các phần còn lại giữ nguyên.
"""
import re

def format_products(products, limit):
    if not products:
        return "(trống - không tìm thấy sản phẩm phù hợp)"
    lines = []
    for p in products[:limit]:
        gia = f"{int(p['gia']):,}".replace(",", ".") + "đ"
        line = f"- {p['ten']} | giá {gia}"
        if p.get("thong_so"):
            line += f" | {p['thong_so']}"
        if p.get("anh"):
            line += f" | ảnh: {p['anh']}"   # ← thêm dòng này
        lines.append(line)
    return "\n".join(lines)

def build_messages(system_prompt, message, history, products, max_turns, max_products):
    """history: [{'role': 'user'|'assistant', 'content': str}, ...]"""
    msgs = [{"role": "system", "content": system_prompt}]
    for h in history[-max_turns * 2:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"][:1000]})
    user = (
        "DANH SÁCH SẢN PHẨM (dữ liệu thật của cửa hàng):\n"
        f"{format_products(products, max_products)}\n\n"
        f"CÂU HỎI CỦA KHÁCH: {message}"
    )
    msgs.append({"role": "user", "content": user})
    return msgs

def clean_reply(text: str) -> str:
    """Bỏ khối <think>...</think> nếu model có suy luận, cắt khoảng trắng thừa."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()

    
