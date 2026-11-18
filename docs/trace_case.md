# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Bảng phân tích chi tiết

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-2f62` |
| Triệu chứng | Grader Lab 8 fail: `status resolved != denied`. Grader Lab 9 fail: `DbFactKept`, `RefundAmountCorrect`. Reply nói *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* trong khi ledger ghi nhận hoàn 20.000đ thay vì 0đ theo nhãn. |
| Bước sai đầu tiên | **Event 3: `kind="model_override"`, payload `{"delay_days": 5}`** |
| Vì sao là bước *đầu tiên* | Bước 1 (`handoff`) và Bước 2 (`investigator`) hoàn toàn đúng: tra cứu DB đơn hàng `O-202` chính xác với `delay_days=2` (chưa đủ điều kiện hoàn). Đến bước 3, agent tự ý tin lời khách hàng trong ticket mà ghi đè dữ liệu DB thành `delay_days=5`. |
| Failure mode | **FM-03 (`ticket_trust`)** trong `docs/failure_taxonomy.md` |
| Đối chứng | Trên shape `fixed` cùng claim C-002@11: Không xuất hiện event `model_override`. Agent giữ nguyên `delay_days=2`, bước 3 tính quote ra 0đ (`no_entitlement`), và bước 4 từ chối hoàn tiền hợp lệ (`status=denied`, `refund_vnd=0`). |
| Regression test | Unit test `test_override_event_breaks_db_fact` trong `tests/test_lab9_graders.py` sử dụng grader `DbFactKept`. Test fail trên variant `seeded_regression` và pass trên `fixed`. |
| Chưa chắc chắn | Trace chỉ ghi nhận agent có override, nhưng không chứng minh được liệu mô hình thực tế bị đánh lừa bởi prompt injection hay do luật suy diễn logic bị lỏng lẻo (ở đây được kích hoạt bởi công tắc `ticket_trust`). |

## Quy tắc áp dụng
- **Ledger trước reply**: Sổ cái ghi nhận hoàn 20.000đ trái phép dù phản hồi văn bản rất trôi chảy.
- **Bước sai đầu tiên**: Xác định chính xác Event 3 (`model_override`) dẫn đến toàn bộ chuỗi sai lệch tính toán sau đó.
