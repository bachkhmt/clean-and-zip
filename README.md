# CleanZip ⚡

**CleanZip** là công cụ đóng gói dự án thông minh: **tự động loại bỏ các file và thư mục rác/nặng** (`node_modules`, `.git`, `__pycache__`, `venv`, `dist`, `.next`, cache, log...) để tạo ra file `.zip` cực kỳ gọn nhẹ và sạch sẽ — lý tưởng để upload lên AI (Claude, ChatGPT, Gemini), gửi cho đồng nghiệp hoặc sao lưu nhanh.

> **An toàn tuyệt đối**: Tool chỉ đọc và nén, **không xóa hay làm thay đổi bất kỳ file nào trong dự án gốc**.

---

## 📁 Chi Tiết Cấu Trúc Thư Mục Dự Án

Cấu trúc mã nguồn của dự án được tổ chức gọn gàng, tách biệt rõ ràng giữa logic cốt lõi, giao diện người dùng và cấu hình loại trừ:

```text
zip-folder/
│
├── 🖥️ GIAO DIỆN & KHỞI CHẠY
│   ├── gui.py                  # Giao diện Desktop UI hiện đại (CustomTkinter)
│   ├── run_gui.bat             # File khởi chạy nhanh giao diện trên Windows (nhấp đúp chuột)
│   └── build_exe.bat           # Script tự động đóng gói ứng dụng thành file CleanZip.exe
│
├── ⚙️ CORE LOGIC & CLI
│   ├── cleanzip.py             # Module xử lý nén chính, lọc file và hỗ trợ chạy dòng lệnh CLI
│   └── default-excludes.txt    # Danh sách các thư mục/file mặc định bị loại trừ (sửa trực tiếp)
│
├── 📦 CẤU HÌNH & DEPENDENCIES
│   ├── requirements.txt        # Danh sách thư viện Python cần thiết (customtkinter, darkdetect)
│   ├── .gitignore              # Loại trừ file rác, file build release nặng (dist, build, *.spec, *.zip)
│   └── README.md               # Tài liệu hướng dẫn sử dụng và cấu trúc dự án
│
└── 🚫 THƯ MỤC BUILD RELEASE (Được .gitignore bỏ qua, không commit lên git)
    ├── dist/                   # Chứa file thực thi CleanZip.exe sau khi build
    ├── build/                  # Thư mục tạm thời trong quá trình PyInstaller build
    └── CleanZip.spec           # File cấu hình đóng gói của PyInstaller
```

### Chi tiết vai trò từng thành phần:

| Tên File / Thư Mục | Loại | Mô tả chức năng |
|---|---|---|
| **`gui.py`** | Source Code | Giao diện Desktop UI xây dựng bằng `CustomTkinter`. Hỗ trợ tự động dán đường dẫn từ clipboard, nén nền (background thread) không bị đơ app, tự động lưu vào `Downloads`, hiển thị dung lượng tiết kiệm được và nút mở trực tiếp thư mục Downloads. |
| **`cleanzip.py`** | Source Code | Chứa core logic: quét cây thư mục (`collect_files`), kiểm tra whitelist/blacklist (`is_excluded`), tính toán dung lượng (`human_size`), nén zip và hỗ trợ giao diện dòng lệnh (CLI). |
| **`default-excludes.txt`** | Config Text | File cấu hình các thư mục và đuôi file bị loại bỏ khi nén. Bạn có thể mở và chỉnh sửa trực tiếp bằng Notepad/VS Code mà không cần động vào mã nguồn Python. |
| **`run_gui.bat`** | Windows Batch | Giúp người dùng Windows khởi chạy ứng dụng Desktop ngay lập tức bằng cách click đúp chuột mà không cần gõ lệnh terminal. |
| **`build_exe.bat`** | Windows Batch | Tự động cài đặt `pyinstaller` (nếu thiếu) và đóng gói toàn bộ dự án thành file thực thi độc lập `CleanZip.exe` nằm trong thư mục `dist/`. |
| **`requirements.txt`** | Config | Khai báo các thư viện Python: `customtkinter` (UI hiện đại) và `darkdetect` (tự động khớp Dark/Light mode hệ điều hành). |
| **`.gitignore`** | Git Config | Chặn các file build phát sinh rất nặng (`dist/`, `build/`, `*.spec`, các file `*.zip` sinh ra) để giữ cho Git repository luôn nhẹ và sạch. |

---

## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Sử Dụng Giao Diện Desktop App (Khuyên dùng)

#### 1. Khởi chạy
- **Cách nhanh nhất**: Nhấp đúp vào biểu tượng shortcut **`CleanZip`** trên màn hình chính Desktop (hoặc nhấp đúp vào file **`run_gui.bat`** trong thư mục dự án).
- Hoặc khởi chạy bằng terminal:
  ```bash
  python gui.py
  ```

#### 2. Thao tác 3 bước đơn giản:
1. **Dán đường dẫn**: Copy đường dẫn thư mục dự án của bạn và ấn nút **"📋 Dán"** (hoặc dùng phím tắt `Ctrl+V`). *Ứng dụng cũng có tính năng tự động nhận diện nếu bạn vừa copy một đường dẫn hợp lệ!*
2. **Bắt đầu Nén**: Nhấp vào nút **"⚡ NÉN DỰ ÁN (ZIP)"**.
3. **Xem kết quả & Lấy file**:
   - File `.zip` sạch sẽ được **tự động lưu vào thư mục `Downloads`** của máy tính bạn theo định dạng `<tên_dự_án>_clean_<thời_gian>.zip`.
   - Hiển thị đầy đủ thông tin: dung lượng file zip, số file đã giữ, dung lượng tiết kiệm được từ việc loại bỏ các file nặng (`node_modules`, `.git`...).
   - Bấm nút **"📂 Mở Thư Mục Downloads"** để xem ngay file zip trong Windows Explorer.

---

### Cách 2: Sử Dụng Dòng Lệnh (CLI)

Thích hợp cho lập trình viên muốn gọi qua Terminal, PowerShell, Alias hoặc tích hợp vào script tự động.

#### Nén mặc định:
```bash
python cleanzip.py "D:\projects\my-web-app"
```
Tool sẽ quét dự án, loại bỏ các thư mục rác theo `default-excludes.txt` và tạo file zip nén sạch.

#### Chỉ định vị trí / tên file zip đầu ra:
```bash
python cleanzip.py "D:\projects\my-web-app" -o "C:\Users\PC\Desktop\my-web-app-clean.zip"
```

#### Xem trước mà không tạo zip (`--dry-run`):
```bash
python cleanzip.py "D:\projects\my-web-app" --dry-run --verbose
```

#### Toàn bộ cờ dòng lệnh:
| Cờ | Tác dụng |
|---|---|
| `source` | Đường dẫn thư mục dự án cần nén (bắt buộc) |
| `-o, --output` | Đường dẫn file zip đầu ra |
| `-e, --exclude` | Thêm các pattern loại trừ tạm thời cho lần chạy này |
| `--excludes-file` | Dùng file cấu hình loại trừ khác thay vì `default-excludes.txt` |
| `--dry-run` | Chỉ quét và thống kê, không tạo file zip |
| `--verbose` | In chi tiết danh sách từng file/thư mục bị bỏ qua |

---

## 🛠️ Tùy Chỉnh Danh Sách Loại Trừ (`default-excludes.txt`)

Mở file `default-excludes.txt` bằng bất kỳ trình soạn thảo nào (VS Code, Notepad...). Mỗi dòng là một thư mục, file hoặc wildcard:

```text
# Bỏ qua dependencies & build
node_modules
dist
build
.next
vendor

# Bỏ qua Python cache & venv
__pycache__
venv
.venv
*.pyc

# Bỏ qua Version Control & IDE
.git
.vscode
.idea
.DS_Store

# Whitelist: Giữ lại file quan trọng (bắt đầu bằng dấu !)
!.env.example
```

- Muốn **thêm** loại trừ mới ➔ Thêm 1 dòng mới vào file.
- Muốn **giữ lại** một loại trừ (ví dụ muốn giữ `dist`) ➔ Thêm dấu `#` ở đầu dòng hoặc xóa dòng đó.
- Muốn **whitelist** ngoại lệ ➔ Dùng dấu `!` ở đầu (ví dụ: `!.env.example`).
- Thay đổi sẽ có hiệu lực ngay lập tức cho cả Desktop UI lẫn CLI mà **không cần sửa code**.

---

## 📦 Đóng Gói Thành Ứng Dụng Độc Lập (`.exe`)

Khi bạn muốn xuất xưởng tool thành 1 file chạy `.exe` độc lập mang sang máy tính khác mà không cần cài đặt Python:

1. Nhấp đúp chuột vào file **`build_exe.bat`**.
2. Script sẽ tự động đóng gói ứng dụng qua PyInstaller.
3. Sau khi hoàn thành, file **`CleanZip.exe`** sẽ nằm sẵn trong thư mục `dist/`.
