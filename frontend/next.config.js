/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: false,
  async headers() {
    return [
      {
        // Dokumen HTML (semua path KECUALI aset _next/) jangan di-cache browser,
        // supaya selalu mengambil HTML segar yang mereferensikan chunk JS terbaru.
        // Mencegah "stale shell" (mis. hanya BBCA tampil) setelah rebuild.
        source: '/((?!_next/).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-store, must-revalidate' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
