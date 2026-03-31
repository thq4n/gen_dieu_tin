# Gen mã Điều tin / Điều nhận

Tool UI chạy local để gen payload theo 4 loại (tương ứng 4 sheet trong `Điều tin - Điều nhận.xlsx`), tự tăng mã mỗi lần gen và lưu output ra file.

## Chạy tool

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

## Output

- `output/<GEN_TYPE_NAME>/*.txt`: payload đã gen (JSON pretty).
- `state/counters.json`: counter dùng để tự tăng `pickupTaskId`/`orderId` theo từng loại.
