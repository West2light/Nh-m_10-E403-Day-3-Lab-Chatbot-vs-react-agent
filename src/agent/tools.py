"""
tools.py - Định nghĩa các tools mà Agent có thể sử dụng
Bao gồm: schema cho Anthropic API và hàm thực thi thực tế
"""

import json
import urllib.parse
import urllib.request
import re

# ─────────────────────────────────────────────
# TOOL SCHEMA (gửi lên Anthropic API)
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_pc_price",
        "description": (
            "Tìm kiếm giá PC / linh kiện máy tính trên web. "
            "Trả về danh sách sản phẩm gồm tên, giá và link trang web. "
            "Dùng tool này khi người dùng hỏi về giá máy tính, laptop, "
            "hay bất kỳ linh kiện PC nào."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Từ khóa tìm kiếm tiếng Việt hoặc tiếng Anh, "
                        "ví dụ: 'PC gaming RTX 4070', 'laptop Dell XPS 15', "
                        "'RAM DDR5 32GB giá rẻ'"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Số kết quả tối đa cần trả về (mặc định: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    }
]

# ─────────────────────────────────────────────
# MOCK DATA – kết quả giả lập thực tế
# (Trong production: thay bằng Google Custom Search API
#  hoặc scrape từ Shopee / Tiki / GeForce / CellphoneS)
# ─────────────────────────────────────────────

_MOCK_DB = {
    "default": [
        {
            "name": "PC Gaming RTX 4070 / Ryzen 7 7700X / 32GB RAM",
            "price": "32.990.000 đ",
            "shop": "GeForce.vn",
            "url": "https://geforce.vn/may-tinh-bo/pc-gaming-rtx4070-r7-7700x",
            "in_stock": True,
        },
        {
            "name": "Máy tính đồng bộ Intel Core i5-13400 / RTX 3060 / 16GB",
            "price": "18.500.000 đ",
            "shop": "Phong Vũ",
            "url": "https://phongvu.vn/p/may-tinh-intel-i5-13400-rtx3060",
            "in_stock": True,
        },
        {
            "name": "PC Văn phòng Intel Core i3-13100 / 8GB / SSD 256GB",
            "price": "7.990.000 đ",
            "shop": "Thế Giới Di Động",
            "url": "https://www.thegioididong.com/tin-tuc/pc-van-phong-i3-13100",
            "in_stock": True,
        },
        {
            "name": "Gaming PC AMD Ryzen 9 7900X / RX 7900 XTX / 64GB DDR5",
            "price": "58.000.000 đ",
            "shop": "Hoàng Hà Mobile",
            "url": "https://hoanghamobile.com/pc-gaming/r9-7900x-rx7900xtx",
            "in_stock": False,
        },
        {
            "name": "Mini PC Intel NUC Core i7-1360P / 16GB / 512GB SSD",
            "price": "14.500.000 đ",
            "shop": "FPT Shop",
            "url": "https://fptshop.com.vn/may-tinh/mini-pc-intel-nuc-i7-1360p",
            "in_stock": True,
        },
    ],
    "laptop": [
        {
            "name": "Laptop Dell XPS 15 9530 / Core i7-13700H / RTX 4060 / 32GB",
            "price": "45.990.000 đ",
            "shop": "Dell Việt Nam",
            "url": "https://www.dell.com/vi-vn/shop/laptops/xps-15-laptop/spd/xps-15-9530-laptop",
            "in_stock": True,
        },
        {
            "name": "Laptop ASUS ROG Zephyrus G14 / Ryzen 9 / RTX 4060",
            "price": "38.500.000 đ",
            "shop": "ASUS Store",
            "url": "https://www.asus.com/vn/laptops/for-gaming/rog-zephyrus/asus-rog-zephyrus-g14-2024/",
            "in_stock": True,
        },
        {
            "name": "Laptop MacBook Pro 14 M3 Pro 18GB/512GB",
            "price": "52.990.000 đ",
            "shop": "Apple Việt Nam",
            "url": "https://www.apple.com/vn/shop/buy-mac/macbook-pro/14-inch",
            "in_stock": True,
        },
    ],
    "ram": [
        {
            "name": "RAM Kingston Fury Beast DDR5 32GB (2x16GB) 5600MHz",
            "price": "2.890.000 đ",
            "shop": "Phong Vũ",
            "url": "https://phongvu.vn/p/ram-kingston-fury-beast-ddr5-32gb-5600mhz",
            "in_stock": True,
        },
        {
            "name": "RAM Corsair Vengeance DDR5 64GB (2x32GB) 6000MHz",
            "price": "5.490.000 đ",
            "shop": "GeForce.vn",
            "url": "https://geforce.vn/ram/corsair-vengeance-ddr5-64gb-6000mhz",
            "in_stock": True,
        },
    ],
    "rtx": [
        {
            "name": "VGA NVIDIA GeForce RTX 4070 SUPER 12GB GDDR6X",
            "price": "16.990.000 đ",
            "shop": "GeForce.vn",
            "url": "https://geforce.vn/vga/rtx-4070-super",
            "in_stock": True,
        },
        {
            "name": "VGA ASUS ROG STRIX RTX 4080 SUPER 16GB OC",
            "price": "28.500.000 đ",
            "shop": "Phong Vũ",
            "url": "https://phongvu.vn/p/vga-asus-rog-strix-rtx4080-super-16gb",
            "in_stock": True,
        },
    ],
}


def _pick_dataset(query: str) -> list:
    """Chọn dataset phù hợp dựa trên từ khóa."""
    q = query.lower()
    if any(k in q for k in ["laptop", "macbook", "notebook", "xps", "rog", "zephyrus"]):
        return _MOCK_DB["laptop"]
    if any(k in q for k in ["ram", "ddr", "memory"]):
        return _MOCK_DB["ram"]
    if any(k in q for k in ["rtx", "rx ", "vga", "gpu", "card màn hình"]):
        return _MOCK_DB["rtx"]
    return _MOCK_DB["default"]

def _price_to_int(price_str: str) -> int:
    digits = re.sub(r"[^\d]", "", price_str)
    return int(digits) if digits else 0

# ─────────────────────────────────────────────
# EXECUTOR – hàm thực thi tool
# ─────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Dispatcher: nhận tên tool + input, trả về chuỗi JSON kết quả.
    Thêm tool mới chỉ cần thêm elif ở đây.
    """
    if tool_name == "search_pc_price":
        return _search_pc_price(**tool_input)
    elif tool_name == "sort_products":
        return _sort_products(**tool_input)

    return json.dumps({"error": f"Tool '{tool_name}' không tồn tại."})


def _search_pc_price(query: str, max_results: int = 5) -> str:
    """
    Tìm kiếm giá PC.
    Trả về JSON string chứa danh sách sản phẩm.
    """
    dataset = _pick_dataset(query)
    results = dataset[:max_results]

    output = {
        "query": query,
        "total_found": len(results),
        "results": results,
        "source_note": (
            "Dữ liệu mô phỏng từ các trang: GeForce.vn, Phong Vũ, "
            "FPT Shop, Thế Giới Di Động, Hoàng Hà Mobile"
        ),
    }
    return json.dumps(output, ensure_ascii=False, indent=2)

def _sort_products(query: str, sort_order: str = "asc", max_results: int = 5) -> str:
    """
    Sắp xếp sản phẩm theo giá.

    Args:
        query: từ khóa tìm kiếm
        sort_order: "asc" = tăng dần, "desc" = giảm dần
        max_results: số lượng kết quả tối đa

    Returns:
        JSON string chứa danh sách sản phẩm đã được sắp xếp
    """
    dataset = _pick_dataset(query)

    reverse = sort_order.lower() == "desc"
    results = sorted(
        dataset,
        key=lambda item: _price_to_int(item.get("price", "0")),
        reverse=reverse,
    )[:max_results]

    output = {
        "query": query,
        "sort_order": sort_order,
        "total_found": len(results),
        "results": results,
        "source_note": "Dữ liệu mô phỏng đã được sắp xếp theo giá",
    }
    return json.dumps(output, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
# TOOLS_OPENAI – schema cho OpenAI API
# (khác Anthropic: bọc trong "function" + "type": "function")
# ─────────────────────────────────────────────

TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "search_pc_price",
            "description": (
                "Tìm kiếm giá PC / linh kiện máy tính trên web. "
                "Trả về danh sách sản phẩm gồm tên, giá và link trang web. "
                "Dùng tool này khi người dùng hỏi về giá máy tính, laptop, "
                "hay bất kỳ linh kiện PC nào."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Từ khóa tìm kiếm tiếng Việt hoặc tiếng Anh, "
                            "ví dụ: 'PC gaming RTX 4070', 'laptop Dell XPS 15'"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Số kết quả tối đa cần trả về (mặc định: 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
        {
        "type": "function",
        "function": {
            "name": "sort_products",
            "description": (
                "Sắp xếp danh sách sản phẩm theo giá tăng dần hoặc giảm dần. "
                "Dùng khi người dùng muốn xem sản phẩm rẻ nhất, đắt nhất, "
                "hoặc sắp xếp theo giá."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Từ khóa tìm kiếm tiếng Việt hoặc tiếng Anh, "
                            "ví dụ: 'RTX 4080 Super', 'laptop Dell XPS', 'RAM DDR5'"
                        ),
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Thứ tự sắp xếp: asc = giá tăng dần, desc = giá giảm dần",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Số kết quả tối đa cần trả về (mặc định: 5)",
                    },
                },
                "required": ["query", "sort_order"],
            },
        },
    }
]