/** API calls go to the FastAPI backend (uvicorn app.main:app). */
const backend = process.env.POKERASSIST_API ?? "http://127.0.0.1:8000";

export default {
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
