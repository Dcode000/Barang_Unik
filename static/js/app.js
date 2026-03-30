// static/js/app.js

console.log("🚀 Engine Barang Unik Siap Mengudara!");

// Helper: Format angka jadi Rupiah (Contoh: 150000 -> Rp 150.000)
const formatUang = (angka) => {
    return new Intl.NumberFormat('id-ID', { 
        style: 'currency', 
        currency: 'IDR', 
        minimumFractionDigits: 0 
    }).format(angka);
};

// Helper: Salin teks ke clipboard (Bisa dipake misal lu mau ngasih fitur "Copy Link Produk")
const copyToClipboard = async (text) => {
    try {
        await navigator.clipboard.writeText(text);
        alert("Link berhasil disalin bre!");
    } catch (err) {
        console.error('Gagal menyalin: ', err);
    }
};
