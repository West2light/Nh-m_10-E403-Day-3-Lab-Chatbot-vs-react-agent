"""
agent.py - Vòng lặp Agent: Thought → Action (Tool Call) → Observation
Sử dụng OpenAI API với tool calling.
Tracking đầy đủ từng bước, tách biệt khỏi UI.
"""

import json
import time
from dataclasses import dataclass, field
from openai import OpenAI

from tools import TOOLS_OPENAI, execute_tool

# ─────────────────────────────────────────────
# DATA CLASSES – cấu trúc tracking
# ─────────────────────────────────────────────

@dataclass
class Step:
    """Một bước trong vòng lặp Agent."""
    step_index: int
    thought: str = ""
    action_tool: str = ""
    action_input: dict = field(default_factory=dict)
    observation: str = ""
    duration_ms: float = 0.0


@dataclass
class AgentTrace:
    """Toàn bộ trace của một lần chạy Agent."""
    user_query: str
    steps: list[Step] = field(default_factory=list)
    final_answer: str = ""
    total_duration_ms: float = 0.0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


# ─────────────────────────────────────────────
# AGENT CLASS
# ─────────────────────────────────────────────

class PCPriceAgent:
    """
    AI Agent tìm kiếm giá PC theo vòng lặp ReAct:
    Thought → Action (tool call) → Observation → ... → Final Answer

    Stopping conditions:
      - Model trả về finish_reason = "stop" (không còn tool call)
      - Vượt quá max_iterations
      - Lỗi xảy ra

    Safety boundaries:
      - Chỉ dùng tool đã định nghĩa trong TOOLS_OPENAI
      - Không thực thi code động
      - Input/output được log đầy đủ
    """

    MODEL = "gpt-4o"
    MAX_ITERATIONS = 5

    SYSTEM_PROMPT = """Bạn là AI Agent chuyên tìm kiếm giá PC, laptop và linh kiện máy tính tại Việt Nam.

## ROLE & RULES
- Trả lời bằng tiếng Việt, thân thiện và chuyên nghiệp.
- Luôn dùng tool `search_pc_price` để tìm kiếm trước khi trả lời.
- Trình bày kết quả rõ ràng: tên sản phẩm, giá, shop, link.
- Nếu không tìm thấy sản phẩm phù hợp, hãy thông báo thẳng thắn.
- KHÔNG bịa đặt giá hay link sản phẩm.

## OUTPUT FORMAT
Sau khi có kết quả từ tool, trả lời theo định dạng:
1. Tóm tắt ngắn về tìm kiếm
2. Danh sách sản phẩm (tên | giá | shop | link)
3. Gợi ý / lời khuyên nếu cần

## STOPPING CONDITION
Dừng sau khi đã có đủ thông tin từ tool và đưa ra câu trả lời hoàn chỉnh."""

    def __init__(self):
        self.client = OpenAI()  # đọc OPENAI_API_KEY từ env

    # ── MAIN ENTRY POINT ──────────────────────────────────────

    def run(self, user_query: str, on_step=None) -> AgentTrace:
        """
        Chạy agent với câu hỏi của người dùng.

        Args:
            user_query: Câu hỏi từ người dùng
            on_step: Callback(step: Step) được gọi sau mỗi bước (dùng cho UI realtime)

        Returns:
            AgentTrace chứa toàn bộ lịch sử và kết quả
        """
        trace = AgentTrace(user_query=user_query, model=self.MODEL)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": user_query},
        ]

        start_total = time.perf_counter()

        for iteration in range(self.MAX_ITERATIONS):
            step = Step(step_index=iteration + 1)
            t0 = time.perf_counter()

            # ── 1. GỌI OPENAI API ─────────────────────────────
            response = self.client.chat.completions.create(
                model=self.MODEL,
                tools=TOOLS_OPENAI,
                tool_choice="auto",
                messages=messages,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            trace.input_tokens  += response.usage.prompt_tokens
            trace.output_tokens += response.usage.completion_tokens

            # ── Trích xuất Thought ──────────────────────────
            step.thought = msg.content or ""

            # ── 2. KIỂM TRA STOPPING CONDITION ─────────────────
            if finish_reason == "stop":
                step.duration_ms = (time.perf_counter() - t0) * 1000
                trace.steps.append(step)
                if on_step:
                    on_step(step)
                trace.final_answer = step.thought
                break

            # ── 3. ACTION – Xử lý tool_calls ───────────────────
            if not msg.tool_calls:
                step.thought = step.thought or "[Agent không quyết định được hành động]"
                trace.steps.append(step)
                if on_step:
                    on_step(step)
                break

            # Thêm assistant message vào history
            messages.append(msg)

            for tool_call in msg.tool_calls:
                step.action_tool  = tool_call.function.name
                step.action_input = json.loads(tool_call.function.arguments)

                # ── 4. OBSERVATION – Thực thi tool ─────────────
                observation_raw  = execute_tool(step.action_tool, step.action_input)
                step.observation = observation_raw

                # Thêm tool result vào history
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      observation_raw,
                })

            step.duration_ms = (time.perf_counter() - t0) * 1000
            trace.steps.append(step)
            if on_step:
                on_step(step)

        trace.total_duration_ms = (time.perf_counter() - start_total) * 1000
        return trace