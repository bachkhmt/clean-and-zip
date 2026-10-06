# CleanZip — Nhật ký thay đổi

## 2.2.0 — 05/10/2026

- Thêm Size Explorer cho cây thư mục, top thư mục/file, quét nền và CLI `--sizes`.
- Ghi ZIP qua file tạm, thay thế nguyên tử khi xong, kẹp timestamp cũ về mốc ZIP hợp lệ và hỗ trợ hủy.
- Bỏ qua symlink, tối ưu so khớp luật, và nén file đã có compression bằng `ZIP_STORED`.
- Đổi luật thư mục chung thành luật chỉ áp dụng ở gốc bằng prefix `/`; thêm file luật riêng trong `~/.cleanzip/`.
- Chuyển cập nhật GUI từ worker sang hàng đợi, lưu cấu hình nguyên tử và sao lưu JSON hỏng thành `.bak`.
- Thêm version module, test suite, tài liệu cập nhật và quy tắc line ending.

## 2.1 — 30/09/2026

### Thêm tính năng loại bỏ file và thư mục tùy chọn

Ngày cập nhật: 30/09/2026
Phiên bản nền: CleanZip v2.1 Pro (chưa đổi số phiên bản)

## 1. Tóm tắt

Trước đây CleanZip chỉ loại bỏ file và thư mục theo danh sách cố định trong `default-excludes.txt` cùng các pattern truyền qua `-e`. Muốn bỏ một file hay thư mục cụ thể của riêng dự án thì phải sửa file cấu hình hoặc tự viết pattern.

Bản này cho phép người dùng chọn trực tiếp file và thư mục cần bỏ:

- Giao diện: thẻ mới "Loại bỏ thêm khỏi file zip" với nút chọn thư mục, chọn file, bỏ từng mục và xóa hết. Danh sách được lưu riêng cho từng dự án.
- Dòng lệnh: cờ mới `-x` / `--exclude-path`.
- Core: cơ chế loại trừ theo đường dẫn chính xác, tách khỏi cơ chế pattern.

Khi không chọn mục nào, CleanZip chạy đúng như trước.

## 2. Các file thay đổi

| File | Thay đổi |
|---|---|
| `cleanzip.py` | Thêm hàm `resolve_exclude_paths`, tham số `exclude_paths`, cờ CLI `-x`, thống kê số file bị loại |
| `gui.py` | Thêm thẻ "Loại bỏ thêm", lưu danh sách theo dự án, vùng chính cuộn được |
| `README.md` | Bổ sung mô tả tính năng, hướng dẫn giao diện, ví dụ và bảng cờ CLI |

Các file còn lại (`default-excludes.txt`, script build, `public/`...) không đổi.

## 3. Lý do dùng cơ chế đường dẫn chính xác

Hàm `is_excluded` hiện có so khớp bằng `fnmatch`, nghĩa là `[`, `]`, `*`, `?` được hiểu là ký tự đặc biệt. Nếu chuyển đường dẫn người dùng chọn thành pattern, thư mục như `app/[id]` (thường gặp trong Next.js) sẽ khớp với `app/i` và `app/d` chứ không phải chính nó.

Vì vậy đường dẫn được chọn không đi qua `is_excluded`. Chúng được đổi thành một tập đường dẫn tương đối đã chuẩn hóa và so sánh bằng phép so khớp chuỗi. Kiểm thử xác nhận `app/[id]` không làm mất `app/i/p.tsx`.

## 4. Thay đổi chi tiết trong `cleanzip.py`

### 4.1. Hàm mới

`_norm_rel(path)`: chuẩn hóa đường dẫn tương đối để so sánh. Đổi `\` thành `/`, bỏ `/` ở hai đầu, không phân biệt hoa thường trên Windows (qua `os.path.normcase`).

`resolve_exclude_paths(source_dir, paths)`: nhận danh sách đường dẫn tuyệt đối hoặc tương đối so với dự án, trả về bộ ba `(rel_set, invalid, missing)`.

- `rel_set`: tập đường dẫn tương đối đã chuẩn hóa, dùng để lọc.
- `invalid`: các mục bị bỏ qua vì nằm ngoài dự án, trỏ vào chính thư mục gốc (`.`), hoặc khác ổ đĩa trên Windows.
- `missing`: các mục hợp lệ nhưng hiện không tồn tại. Chúng vẫn nằm trong `rel_set`.

Chuỗi rỗng bị bỏ qua, dấu nháy đơn/kép ở hai đầu được gỡ. Với đường dẫn tương đối, `\` được đổi thành `/` trước khi chuẩn hóa để chuỗi kiểu Windows như `src\utils\old.py` hoạt động cả trên Linux và macOS.

### 4.2. Hàm đã sửa

`collect_files(source_dir, patterns, verbose_skip=False, exclude_paths=None)`

- Thêm tham số `exclude_paths` (tập đường dẫn đã chuẩn hóa).
- Một thư mục hoặc file bị loại nếu nằm trong `exclude_paths` hoặc khớp `is_excluded`. Kiểm tra `exclude_paths` đứng trước, nên lựa chọn của người dùng thắng cả whitelist `!` (ví dụ chọn `.env.example` để loại thì nó bị loại).
- Thư mục bị loại vẫn được cắt khỏi `os.walk` nên không quét vào bên trong.
- Giá trị trả về đổi từ 4 phần tử thành 5: thêm `skipped_files_count`. Số này đếm mọi file bị loại theo tên file, cả do pattern lẫn do đường dẫn chọn tay. File nằm trong thư mục bị loại không được đếm riêng vì thư mục đã bị cắt.

`zip_project(...)`

- Thêm tham số `exclude_paths: list = None`, đặt sau `extra_excludes` và trước `include_media`.
- Gọi `resolve_exclude_paths` trước khi quét.
- Dict kết quả có thêm ba khóa: `skipped_files_count`, `invalid_exclude_paths`, `missing_exclude_paths`.

### 4.3. Dòng lệnh

Cờ mới: `-x PATH`, `--exclude-path PATH`. Dùng `action="append"` nên lặp lại được nhiều lần:

```bash
python cleanzip.py "D:\my-app" -x docs/old-report.pdf -x data/raw -x assets/videos
```

- Đường dẫn tương đối tính từ thư mục dự án; đường dẫn tuyệt đối phải nằm trong dự án.
- Mục nằm ngoài dự án hoặc không tồn tại được cảnh báo ra `stderr`.
- Dòng thống kê đổi từ `Bỏ qua: N thư mục` thành `Bỏ qua: N thư mục, M file`.

Cờ `-e` (pattern, có wildcard) giữ nguyên hành vi.

### 4.4. Lưu ý tương thích

- Gọi `zip_project` bằng tham số có tên (như `gui.py` đang làm) không bị ảnh hưởng. Mã bên ngoài gọi theo vị trí và truyền `include_media` làm tham số thứ năm sẽ bị lệch do `exclude_paths` chèn vào trước nó.
- Mã bên ngoài gọi trực tiếp `collect_files` và gán kết quả vào 4 biến cần thêm biến thứ năm.

## 5. Thay đổi chi tiết trong `gui.py`

### 5.1. Giao diện

Thẻ mới đặt giữa khung nhập đường dẫn và nút "NÉN DỰ ÁN":

- Nút "Thêm thư mục": mở hộp thoại chọn một thư mục, mở sẵn tại thư mục dự án.
- Nút "Thêm file": mở hộp thoại chọn một hoặc nhiều file.
- Nút "Xóa hết": làm trống danh sách, bị vô hiệu hóa khi danh sách rỗng.
- Nhãn đếm số mục ở góc phải tiêu đề thẻ.
- Danh sách mục: mỗi dòng gồm biểu tượng thư mục/file, đường dẫn tương đối (thư mục có thêm dấu `/` ở cuối, đường dẫn dài được rút gọn ở giữa) và nút ✖ để bỏ mục đó. Mục không còn tồn tại được tô màu vàng kèm chữ "không còn tồn tại".

Vùng chính đổi từ `CTkFrame` sang `CTkScrollableFrame` để thẻ mới không làm nội dung bị cắt trên màn hình thấp. Kích thước cửa sổ:

| | Trước | Sau |
|---|---|---|
| Kích thước ban đầu | 760x690 | 760 x `min(860, max(600, chiều cao màn hình - 100))` |
| Kích thước tối thiểu | 720x640 | 720x560 |

Sau khi nén xong, vùng chính tự cuộn xuống để thấy khung kết quả.

### 5.2. Quy tắc khi thêm mục

- Phải chọn dự án hợp lệ trước. Nếu chưa, hộp thoại nhắc và không mở cửa sổ chọn.
- Mục nằm ngoài dự án hoặc là chính thư mục gốc bị bỏ qua, có hộp thoại cảnh báo (liệt kê tối đa 5 mục).
- Mục đã có, hoặc đã nằm trong một thư mục đang bị loại, không được thêm lần nữa.
- Khi thêm một thư mục bao trùm các mục con đã chọn trước đó, các mục con được gộp vào thư mục mới.
- Danh sách luôn sắp xếp thư mục trước, file sau, theo thứ tự chữ cái.
- Thanh trạng thái báo số mục vừa thêm và số mục bị bỏ qua vì trùng.

### 5.3. Lưu theo từng dự án

Danh sách được ghi vào `~/.cleanzip_config.json` ngay sau mỗi thay đổi, dưới khóa mới `project_excludes`:

```json
{
  "project_excludes": {
    "d:\\projects\\my-app": [
      {"path": "data/raw", "kind": "dir"},
      {"path": "docs/old-report.pdf", "kind": "file"}
    ]
  }
}
```

- Khóa là đường dẫn dự án sau `normpath` và `normcase`, nên trên Windows không phân biệt hoa thường.
- Chỉ nhớ tối đa 30 dự án. Dự án dùng gần nhất nằm cuối, khi vượt giới hạn thì dự án cũ nhất bị bỏ.
- Danh sách trống thì khóa của dự án đó bị xóa khỏi file cấu hình.
- Dữ liệu sai định dạng (sửa tay file cấu hình) được bỏ qua thay vì gây lỗi.
- File cấu hình cũ không có khóa này vẫn đọc bình thường.

Việc nạp danh sách được gọi khi: dán đường dẫn, chọn qua nút Duyệt, chọn từ danh sách "Gần đây", bấm Xóa hoặc "Nén dự án khác", clipboard tự nhận diện, và khi gõ trực tiếp vào ô đường dẫn (chờ 350 ms sau lần gõ cuối). Ngoài ra danh sách được đồng bộ lại ngay trước khi nén để tránh lệch khi vừa gõ xong đã bấm nén.

### 5.4. Trong lúc nén

Ba nút của thẻ bị vô hiệu hóa, các thao tác bỏ mục và xóa hết bị chặn. Danh sách được sao chép trước khi tạo luồng nén nên thay đổi ở ô đường dẫn trong lúc đó không ảnh hưởng lần nén đang chạy. Nút được bật lại khi xong hoặc khi lỗi.

### 5.5. Khung kết quả

- Ô "Tiết kiệm được" hiển thị `N thư mục, M file bị loại` thay cho `N thư mục rác`.
- Phần chi tiết thêm dòng "Loại bỏ thêm theo lựa chọn của bạn: X mục" khi có mục chọn tay.
- Nếu có mục không còn tồn tại, hiện thêm dòng cảnh báo mục đó không có tác dụng.

### 5.6. Hàm và biến mới

| Tên | Vai trò |
|---|---|
| `_nk`, `_shorten` (cấp module) | Khóa so sánh đường dẫn; rút gọn chuỗi dài |
| `excl_items`, `excl_key`, `_sync_job` | Danh sách hiện tại, khóa dự án sở hữu danh sách, tác vụ debounce |
| `_current_project`, `_project_key` | Lấy dự án hợp lệ đang nhập; tạo khóa lưu trữ |
| `_schedule_sync_excludes`, `_sync_project_excludes` | Debounce và nạp danh sách của dự án |
| `_persist_excludes`, `_render_excludes` | Ghi cấu hình; vẽ lại danh sách |
| `_require_project` | Kiểm tra đã chọn dự án trước khi mở hộp thoại |
| `add_exclude_folder`, `add_exclude_files`, `_add_excludes` | Thêm mục và áp quy tắc ở mục 5.2 |
| `remove_exclude`, `clear_excludes` | Bỏ một mục; xóa hết |
| `_set_exclude_controls` | Bật/tắt nút trong lúc nén |
| `_scroll_to_bottom` | Cuộn xuống khung kết quả |

`_run_zip` nhận thêm tham số `exclude_paths` và bổ sung `manual_excluded` vào dict kết quả để hiển thị.

## 6. Kiểm thử

### 6.1. Logic core

Chạy trên một dự án mẫu gồm thư mục có `[ ]`, file có `( )`, `node_modules`, `.env`, `.env.example`:

- Loại thư mục và file bằng đường dẫn tương đối, tuyệt đối, có `./` ở đầu, và có `\` kiểu Windows: đúng.
- `app/[id]` không làm mất `app/i/p.tsx`: đúng.
- Mục ngoài dự án (`../outside`, `..`, `.`, đường dẫn tuyệt đối ngoài dự án, chính thư mục gốc) được đưa vào `invalid`: đúng.
- Mục không tồn tại được đưa vào `missing`, không gây lỗi: đúng.
- Chọn `.env.example` (nằm trong whitelist) thì file bị loại: đúng.
- Không truyền `exclude_paths`: kết quả không đổi so với trước; chế độ `--dry-run` chạy bình thường.
- CLI với `-x` lặp lại, kèm cảnh báo ra `stderr`: đúng.

### 6.2. Giao diện

Chạy `gui.py` thật trên màn hình ảo (Xvfb, Python 3.12, customtkinter 6.0.0). Hộp thoại chọn file/thư mục được thay bằng giá trị cố định trong script, các phần còn lại chạy qua mainloop thật:

- Bấm thêm khi chưa chọn dự án: hiện nhắc, không lỗi.
- Thêm thư mục, nhiều file, mục ngoài dự án, mục trùng, mục con của thư mục đã chọn: kết quả đúng như mục 5.2.
- Danh sách được ghi vào file cấu hình; đổi sang dự án khác thì danh sách trống, quay lại thì nạp lại đúng.
- Nén thật: file zip không chứa các mục đã chọn, vẫn chứa mục vừa bỏ chọn.
- Đổi tên một thư mục đã chọn: mục hiện cảnh báo "không còn tồn tại".
- "Xóa hết" làm trống danh sách và xóa khóa tương ứng trong file cấu hình.

### 6.3. Chưa kiểm tra

- Chưa chạy trên Windows và macOS thật. Hộp thoại chọn file/thư mục gốc của hệ điều hành chỉ được mô phỏng.
- Chưa build lại `.exe` / `.app` bằng PyInstaller. Không thêm dependency mới nên script build không cần sửa.
- `_scroll_to_bottom` dùng thuộc tính nội bộ `_parent_canvas` của customtkinter và được bọc `try/except`. Nếu phiên bản thư viện đổi tên thuộc tính này thì chỉ mất tính năng tự cuộn, không gây lỗi.

## 7. Giới hạn hiện tại

- Hộp thoại chọn thư mục của tkinter chỉ chọn được một thư mục mỗi lần. File thì chọn nhiều được.
- Trong giao diện chưa có ô nhập pattern có wildcard (như `*.log`). Pattern vẫn dùng được qua `-e` hoặc `default-excludes.txt`.
- Danh sách gắn với đường dẫn dự án. Nếu di chuyển hoặc đổi tên thư mục dự án, danh sách cũ không tự chuyển theo.
- Loại một thư mục sẽ loại toàn bộ bên trong, không thể loại thư mục nhưng giữ lại một file con bằng cách chọn trong giao diện.
