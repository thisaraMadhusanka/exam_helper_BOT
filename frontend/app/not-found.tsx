import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#07080E] text-white">
      <h2 className="text-xl font-bold">Page Not Found</h2>
      <p className="mt-2 text-sm text-gray-400">Could not find requested resource</p>
      <Link
        href="/"
        className="mt-4 rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white hover:bg-purple-500"
      >
        Return Home
      </Link>
    </div>
  );
}

