async function decryptAndDownload(fileId){

    const response = await fetch("/download/"+fileId);

    const data = await response.json();

    const encryptedFile = base64ToArrayBuffer(data.encrypted_file);
    const encryptedAES = base64ToArrayBuffer(data.encrypted_aes_key);

    const privateKeyBase64 = sessionStorage.getItem("private_key");

    const privateKey = await crypto.subtle.importKey(
        "pkcs8",
        base64ToArrayBuffer(privateKeyBase64),
        {name:"RSA-OAEP",hash:"SHA-256"},
        false,
        ["decrypt"]
    );

    const aesKeyRaw = await crypto.subtle.decrypt(
        {name:"RSA-OAEP"},
        privateKey,
        encryptedAES
    );

    const aesKey = await crypto.subtle.importKey(
        "raw",
        aesKeyRaw,
        {name:"AES-GCM"},
        false,
        ["decrypt"]
    );

    const iv = encryptedFile.slice(0,12);
    const fileData = encryptedFile.slice(12);

    const decrypted = await crypto.subtle.decrypt(
        {name:"AES-GCM",iv:iv},
        aesKey,
        fileData
    );

    const blob = new Blob([decrypted]);

    const link = document.createElement("a");

    link.href = URL.createObjectURL(blob);

    link.download = "file";

    link.click();
}

function base64ToArrayBuffer(base64){

    const binary = atob(base64);

    const bytes = new Uint8Array(binary.length);

    for(let i=0;i<binary.length;i++){
        bytes[i]=binary.charCodeAt(i);
    }

    return bytes.buffer;
}