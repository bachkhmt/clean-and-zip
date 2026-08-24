# cleanzip

Đóng zip 1 dự án, **tự động loại bỏ** các thư mục/file nặng như `node_modules`,
`.git`, `__pycache__`, `venv`, `dist`... để có bản zip gọn, sạch — dùng để
upload lên AI, gửi cho người khác, backup nhanh...

**Không đụng vào dự án gốc** — chỉ đọc và nén, không xóa gì trong dự án thật.
Dự án gốc vẫn còn nguyên `node_modules`, chạy bình thường như chưa có gì xảy ra.

---

## Cấu trúc dự án (2 file, đúng 2 việc riêng biệt)

```
cleanzip/
├── cleanzip.py             <- Code chạy tool (KHÔNG cần sửa)
└── default-excludes.txt    <- Danh sách thư mục/file mặc định bị loại (sửa ở đây)
```

- **`cleanzip.py`**: bạn chạy file này, kèm theo đường dẫn thư mục dự án muốn zip.
  Đây là phần **bạn chỉ định** mỗi lần chạy.
- **`default-excludes.txt`**: danh sách những gì sẽ tự động bị loại (`node_modules`,
  `__pycache__`, `.git`, `venv`, `dist`,...). File này **tách riêng khỏi code**,
  bạn mở bằng bất kỳ trình soạn thảo text nào để thêm/bớt, không cần biết code Python.

---

## Cách dùng

### Bước 1 — Chỉ định thư mục dự án cần zip

```bash
python3 cleanzip.py /duong/dan/den/du-an-A
```

Chỉ vậy là xong. Tool sẽ tự đọc `default-excludes.txt` (nằm cùng thư mục với
`cleanzip.py`) và loại bỏ đúng những gì được liệt kê trong đó, rồi nén phần còn
lại thành file `.zip`.

Kết quả mặc định: `du-an-A_clean_20260819_140530.zip` được tạo trong thư mục
hiện tại (nơi bạn đang đứng khi chạy lệnh).

### Bước 2 (tùy chọn) — Chỉ định tên/vị trí file zip đầu ra

```bash
python3 cleanzip.py /duong/dan/den/du-an-A -o ~/Desktop/du-an-A-clean.zip
```

### Bước 3 (tùy chọn) — Xem trước, chưa nén thật

Muốn biết chắc thứ gì sẽ bị giữ / bị loại trước khi tạo file zip thật:

```bash
python3 cleanzip.py /duong/dan/den/du-an-A --dry-run --verbose
```

`--dry-run` = không tạo file zip, chỉ liệt kê.
`--verbose` = in ra từng thư mục/file cụ thể bị bỏ qua (không có cờ này thì chỉ
in tóm tắt).

---

## Sửa danh sách loại trừ mặc định

Mở file `default-excludes.txt` bằng bất kỳ trình soạn thảo nào (VS Code, Notepad,
nano...), mỗi dòng là 1 thư mục/file/pattern sẽ bị loại:

```
# Dòng bắt đầu bằng # là ghi chú, bị bỏ qua
node_modules
__pycache__
.git
venv
dist
*.log
```

- Muốn **thêm** loại trừ mới → thêm 1 dòng mới, gõ tên thư mục hoặc pattern
  (có thể dùng `*` để khớp nhiều file, ví dụ `*.sqlite3`)
- Muốn **bỏ** một loại trừ có sẵn (ví dụ bạn vẫn muốn giữ `dist/`) → xóa dòng
  đó đi hoặc thêm `#` vào đầu dòng để tắt tạm thời
- Sửa xong, lưu file lại — lần chạy `cleanzip.py` tiếp theo sẽ áp dụng ngay,
  **không cần sửa code**

Danh sách mặc định có sẵn đã bao phủ hầu hết các loại dự án phổ biến:

| Nhóm | Loại trừ |
|---|---|
| JavaScript/Node | `node_modules`, `dist`, `build`, `.next`, `.nuxt`, `coverage`, ... |
| Python | `__pycache__`, `venv`, `.venv`, `*.pyc`, `.pytest_cache`, ... |
| Java/Gradle | `target`, `.gradle` |
| PHP | `vendor` |
| Version control/IDE | `.git`, `.svn`, `.idea`, `.vscode`, `.DS_Store` |
| Log/cache chung | `*.log`, `.cache`, `tmp`, `temp` |

## Loại trừ thêm chỉ cho 1 lần chạy (không sửa file)

Nếu chỉ muốn loại thêm thứ gì đó cho **riêng lần chạy này**, không muốn thêm
vĩnh viễn vào `default-excludes.txt`:

```bash
python3 cleanzip.py /duong/dan/den/du-an-A -e "uploads" "*.sqlite3"
```

## Dùng file danh sách loại trừ khác (nếu có nhiều bộ khác nhau)

```bash
python3 cleanzip.py /duong/dan/den/du-an-A --excludes-file /path/to/excludes-rieng.txt
```

---

## Toàn bộ tùy chọn dòng lệnh

| Cờ | Ý nghĩa |
|---|---|
| `source` (bắt buộc) | Đường dẫn thư mục dự án cần zip — đây là phần bạn "chỉ định" |
| `-o, --output` | Đường dẫn file zip đầu ra |
| `-e, --exclude` | Thêm pattern loại trừ tạm thời, chỉ áp dụng lần chạy này |
| `--excludes-file` | Dùng file danh sách loại trừ khác thay vì `default-excludes.txt` |
| `--dry-run` | Chỉ liệt kê, không tạo file zip |
| `--verbose` | In chi tiết từng file/thư mục bị bỏ qua |

---

## Chạy gọn hơn bằng alias (tùy chọn)

Thêm vào `~/.bashrc` hoặc `~/.zshrc`:

```bash
alias cleanzip="python3 /duong/dan/toi/cleanzip/cleanzip.py"
```

Sau đó chỉ cần:

```bash
cleanzip ~/projects/du-an-A
```

---

## Tóm tắt luồng sử dụng

1. Có dự án A cần đóng gói gọn để đưa lên AI
2. Chạy: `python3 cleanzip.py /path/to/du-an-A`
3. Tool tự đọc `default-excludes.txt`, loại `node_modules`/`.git`/`__pycache__`/...
4. Ra file `du-an-A_clean_....zip` — nhẹ, sạch, sẵn sàng upload
5. Dự án A gốc **không hề bị thay đổi** — muốn chạy lại vẫn chạy bình thường,
   không cần cài lại gì
