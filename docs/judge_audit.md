# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.800 ≥ 0.7) | DÙNG |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (R=0.300 < 0.7, κ=0.375 < 0.6) | LOẠI |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Đề xuất sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người đúng | Câu văn: *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* Giọng điệu suồng sã, xưng "em - anh" thiếu chuyên nghiệp so với tiêu chuẩn CSKH chuẩn của LogiX. **Sửa rubric:** Thêm quy tắc cấm xưng hô thân mật tự phát, bắt buộc tuân thủ xưng danh thương hiệu (*"Dạ, LogiX..."*). |
| 2 | H-017 | PASS | FAIL | Người đúng | Câu văn: *"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."* Sử dụng khẩu ngữ *"bạn ơi... nha"*. Judge dễ dãi vì thấy có thông tin tiền hoàn và từ "Dạ". **Sửa rubric:** Bắt buộc loại bỏ từ ngữ khẩu ngữ đuôi câu thân mật cợt nhả (*"nha", "nhé", "nè"*). |
| 3 | H-029 | PASS | FAIL | Người đúng | Câu văn: *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* Giọng điệu cụt lủn, mang tính xua đuổi khách hàng (*"không cần nhắn thêm"*). Judge chấm sót (FN). **Sửa rubric:** Bổ sung tiêu chí cấm thái độ thô lỗ, áp đặt hoặc từ chối hỗ trợ tiếp. |
| 4 | H-042 | FAIL | PASS | Người đúng | Câu văn: *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* Phản hồi trang trọng, rõ ràng và cung cấp thêm thời gian tiền về (3-5 ngày). Judge quá khắt khe chấm FAIL (FP). **Sửa rubric:** Nêu rõ việc cung cấp mốc thời gian ước tính là hành vi tích cực, không phải là phát ngôn ngoài thẩm quyền nếu nằm trong khung xử lý. |
| 5 | HL-016 | PASS | FAIL | Người đúng | Câu văn: *"Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của..."* Khách yêu cầu hoàn tiền nhưng agent chỉ xin lỗi sáo rỗng, không cung cấp giải pháp hoặc trạng thái đơn hàng. Judge bị đánh lừa bởi văn phong lịch sự. **Sửa rubric helpful:** Định nghĩa helpful phải giải quyết dứt điểm câu hỏi hoặc hướng dẫn bước tiếp theo rõ ràng; lời xin lỗi suông không kèm hành động cụ thể phải chấm FAIL. |

## Kết luận
- **Tiêu chí bị loại và lý do**:
  - `helpful` bị loại hoàn toàn khỏi CI gate do vi phạm nghiêm trọng ngưỡng trần độ tin cậy.
  - Ma trận nhầm lẫn của `helpful`: `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}`.
  - Tỉ lệ bỏ sót (False Negative) lên tới 21/30 trường hợp (Recall chỉ đạt $30.0\%$, thấp hơn nhiều so với ngưỡng yêu cầu $\ge 70\%$). Hệ số nhất quán Cohen's Kappa chỉ đạt $0.375$ (dưới ngưỡng sàn $0.6$).
  - Judge `helpful` có xu hướng bị đánh lừa bởi các câu trả lời mang tính ngoại giao, lịch sự hoặc xin lỗi chung chung mà không thực sự xử lý vấn đề của khách hàng (lenient judge).
- **Rủi ro còn lại**:
  - Judge `tone_ok` chỉ được kiểm thử trên tập replay đã công khai (100 mẫu). Cần liên tục thu thập mẫu hội thoại thực tế của người dùng để gán nhãn held-out mới nhằm tránh data drift và overfitting vào phong cách viết của tập replay.
