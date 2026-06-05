import { NextResponse } from "next/server";

// Auth désactivé — accès libre pour le développement/test
export async function middleware() {
  return NextResponse.next();
}