Tôi muốn bạn hãy implement toàn bộ frontend bản web cho ứng dụng này

Têu cầu:

- Mobile first/responsive
- Sử dụng theme mặc định của shadcn, sử dụng giao diện hiện đại của shadcn.
- Thể hiện được toàn bộ tính năng của ứng dùng (xem code backend)
- Giao diện hợp lý, khoa học - không phải mapping 1-1 từ code backend hoặc database sang UI. Bạn cần phải phân tích và thiết kế lại giao diện dựa trên nhu cầu người dùng và tính năng của ứng dụng từ project của backend rồi mới thiết kế ra giao diện frontend.
- Bắt buộc luôn load các skill sau khi implement: taste frontend skill, shadcn skill (bắt buộc với mọi phase FE)
- Xóa bỏ hoàn toàn các component cũ, cấm ghi nhớ layout cũ rồi bản mới chỉ đơn giản là layout cũ + thay đổi màu sắc
- cấm mapping 1-1 từ folder structure của backend sang frontned. Phải từ backend + docs hình dùng ra thiết kế của ứng dụng -> bắt đầu thiết kế ra giao diện frontend phù hợp
- tại mỗi bước bắt buộc implement e2e testing để đảm bảo tính năng hoạt động đúng, không chỉ test unit mà còn test toàn bộ flow của ứng dụng.
- tất cả component ngoại trừ shadcn bắt buộc phải có storybook để test và demo component đó, không được bỏ qua bước này.
- cho phép trực tiếp truy cập và chỉnh sửa 2 project backend.
- Cấm việc tạo ra 1 sản phẩm "chạy được", tôi cần 1 ứng dụng hoàn chỉnh/đầy đủ từ những thứ nhỏ nhặt nhất đến tính năng lớn, kể cả những thứ nice to have như drag and drop file, ... Ứng dụng phải có tính cạnh tranh, hiện đại, thuận tiện.

Các bước thực hiện (lưu ý đây là các bước lớn, mỗi bước có thể trải dài nhiều phase):

1. Xóa toàn bộ component cũ và layout cũ.
2. Đưa ra một bản design đề xuất, lưu design trong file DESIGN.md (tham khảo repo https://github.com/google-labs-code/design.md)
3. Tìm và implement các phần code hoặc tính năng mà backend thiếu hoặc cần thêm để phục vụ cho frontend (ở cả 2 repo openlet và )
4. Triển khai implement giao diện của toàn bộ giao diện với toàn bộ tính năng của ứng dụng.

có thể triển khai không giới hạ số phase và độ dài tài liệu vì đây là implement toàn bộ frontend trong 1 plan duy nhất

OUTPUT bắt buộc phải là 1 ứng dụng có thể chạy được mọi tính năng trên cả mobile và desktop, sản phẩm sẽ được giao trực tiếp cho khách hàng mà không có con người trực tiếp kiểm thử QC hay tester

spawn subagent để tìm hiểu về openlet project
