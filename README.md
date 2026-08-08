# VaultSync
A secure cloud file-sharing system using hybrid RSA-AES encryption, user-based access control, access requests, and time-limited file sharing.
# VaultSync 🔐

VaultSync is a secure cloud-based file storage and sharing system designed to protect user files through encryption and controlled access. The system combines **AES encryption for file data** with **RSA encryption for secure key protection**, providing a hybrid cryptographic approach for secure cloud file storage.

## 🚀 Features

- 🔐 Secure user registration and authentication
- 📁 Secure file upload and storage
- 🔒 AES-based file encryption
- 🔑 RSA-based AES key protection
- 👤 User-based file sharing
- 📩 Access request mechanism
- ✅ File access approval and rejection
- ⏳ Time-limited file access
- 🔔 Access approval/rejection notifications
- 📥 Secure file download and decryption
- 📋 File access and activity management
- 🛡️ Protection against unauthorized file access

## 🔑 Security Approach

VaultSync uses a hybrid encryption mechanism:

**AES Encryption**
- Used to encrypt the actual file contents.
- Provides efficient encryption for files of different sizes.

**RSA Encryption**
- Used to securely protect the AES encryption key.
- Provides secure key exchange and controlled access.

The overall process is:

```text
File
  ↓
AES Encryption
  ↓
Encrypted File
  +
RSA-Encrypted AES Key
  ↓
Secure Cloud Storage
When an authorized user downloads a file:
Encrypted File
  ↓
AES Decryption
  ↓
Original File

👥 Access Control

VaultSync provides user-based access control for shared files.

A file owner can:

Share a file with specific users
Receive access requests
Grant access
Reject access
Control the duration of access

Users who do not have permission cannot directly access protected files.

🔄 File Sharing Workflow
File Owner
    ↓
Select File
    ↓
Select User
    ↓
Share File
    ↓
User Receives Shared File
    ↓
User Requests Access (if required)
    ↓
Owner Reviews Request
    ↓
 ┌───────────────┐
 │               │
Grant          Reject
 │               │
 ↓               ↓
Access         Access Denied

📊 Performance Evaluation

The system was evaluated based on the overhead introduced by encryption and decryption.

The evaluation includes:

File upload time
File download and opening time
Storage size before and after encryption

The experimental results show that encrypted files require slightly more processing time because encryption and decryption introduce additional computational operations. However, the overhead remains practical for moderate file sizes.

The storage evaluation also shows that encryption introduces minimal additional storage overhead.

🖥️ Main Modules
1. Authentication

Provides secure user registration and login.

2. My Files

Allows users to manage their uploaded files.

3. File Upload

Users can upload files that are encrypted before storage.

4. File Sharing

Allows owners to share files with selected users.

5. Shared With Me

Displays files shared with the current user.

6. Access Requests

Allows file owners to review and approve or reject access requests.

7. Notifications

Notifies users when their access requests are approved or rejected.

8. Secure File Access

Authorized users can securely download and access shared files.

🛠️ Technologies Used
Python
Django
HTML
CSS
JavaScript
AES Encryption
RSA Encryption
SQLite / Database
Cryptography Libraries

🔒 Security Benefits

VaultSync is designed to provide:

Confidentiality – Files are encrypted before storage.
Controlled Access – Only authorized users can access shared files.
Secure Key Protection – RSA is used to protect AES encryption keys.
User-Based Sharing – File owners decide who can access their files.
Time-Limited Access – Shared access can expire after a specified period.
Access Management – Owners can approve or reject access requests.
📈 Evaluation

The system demonstrates that hybrid encryption provides strong file protection while maintaining practical performance.

Although encryption and decryption introduce additional processing time compared with non-encrypted file operations, the measured overhead remains reasonable for typical file-sharing scenarios.

🎯 Objective

The primary objective of VaultSync is to provide a secure and controlled environment for storing and sharing files in the cloud while reducing the risks associated with unauthorized access and unprotected data.

🔮 Future Scope

Possible future improvements include:

Multi-factor authentication
Advanced audit logging
Attribute-based access control
Blockchain-based access records
Intrusion detection
Multi-cloud storage
Advanced key management
Post-quantum cryptographic techniques
👩‍💻 Project

VaultSync – Secure Cloud File Sharing System

Developed as an academic cybersecurity/cloud-storage project focusing on secure file storage, hybrid encryption, and controlled file sharing.
