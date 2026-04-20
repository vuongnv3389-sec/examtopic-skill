# ExamTopics Pipeline

## Giới thiệu
ExamTopics Pipeline là bộ công cụ hỗ trợ thu thập và trích xuất dữ liệu từ các topic ExamTopics, bao gồm danh sách discussion, HTML nội dung thảo luận, và bộ câu hỏi đáp án theo từng exam code.

## IDE sử dụng
- Khuyến nghị dùng VS Code để mở thư mục `examtopics-pipeline/` và chỉnh sửa các file `SKILL.md`, `README.md`, và `scripts/`.
- Có thể dùng Explorer, Command Palette, và terminal tích hợp của VS Code để chạy lệnh cài đặt và kiểm tra nhanh.

## Mục đích
Dùng để chuẩn hóa quá trình lấy dữ liệu ExamTopics theo từng topic hoặc từng exam code, giúp việc thống kê, lọc và xuất kết quả trở nên nhanh hơn, nhất quán hơn, và dễ tái sử dụng.

## Công dụng
- Lấy danh sách link discussion theo topic.
- Đếm và thống kê exam code xuất hiện trong một topic.
- Tải HTML discussion cho một exam code cụ thể.
- Trích xuất câu hỏi và đáp án từ dữ liệu đã tải.
- Xuất kết quả ra CSV và JSON để phục vụ phân tích tiếp theo.

## Thành phần chính
- `fetch_discussion_pages.py`: thu thập link discussion theo topic.
- `fetch_question_response_bodies.py`: tải nội dung HTML theo exam code.
- `extract_question_answers.py`: trích xuất câu hỏi và đáp án từ HTML.

## Đầu ra điển hình
- `discussion_links.csv`
- `question-response-bodies/`
- `<exam_code>_questions.csv`
- `<exam_code>_questions_detailed.json`

## Cấu trúc lưu trữ
Dữ liệu nên được lưu theo dạng:
`./<topic>/scan_<timestamp>/`

Cấu trúc này giúp dễ theo dõi từng lần quét, tái xử lý, và so sánh kết quả giữa các lần chạy.

## Cài đặt vào `~/.claude/skills/`
1. Clone repository về máy:

```bash
git clone https://github.com/vuongnv3389-sec/examtopic-skill.git
```

2. Tạo thư mục đích nếu chưa có:

```bash
mkdir -p ~/.claude/skills/examtopics-pipeline/
```

3. Chép toàn bộ file của skill vào thư mục đó:

```bash
cd examtopic-skill
cp SKILL.md ~/.claude/skills/examtopics-pipeline/
cp -r scripts ~/.claude/skills/examtopics-pipeline/
```

4. Mở thư mục skill trong VS Code để kiểm tra lại cấu trúc:

```bash
code ~/.claude/skills/examtopics-pipeline/
```

5. Xác nhận bên trong thư mục đích có đủ `SKILL.md` và `scripts/`.
