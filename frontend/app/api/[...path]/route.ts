import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getTargetBase(): string {
  const base =
    process.env.API_BASE_INTERNAL ||
    process.env.NEXT_PUBLIC_API_BASE ||
    "http://127.0.0.1:8000";
  return base.replace(/\/+$/, "");
}

async function proxyRequest(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const pathSegments = params.path || [];
  const subPath = pathSegments.map((s) => encodeURIComponent(s)).join("/");
  const search = request.nextUrl.search;
  const targetBase = getTargetBase();
  const targetUrl = `${targetBase}/${subPath}${search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey !== "host" &&
      lowerKey !== "connection" &&
      lowerKey !== "content-length"
    ) {
      headers.set(key, value);
    }
  });

  const method = request.method;
  let body: BodyInit | undefined = undefined;

  if (method !== "GET" && method !== "HEAD") {
    const contentType = request.headers.get("content-type") || "";
    if (contentType.includes("multipart/form-data")) {
      body = await request.formData();
      // Remove content-type so fetch sets the boundary automatically
      headers.delete("content-type");
    } else {
      body = await request.arrayBuffer();
    }
  }

  try {
    const upstreamRes = await fetch(targetUrl, {
      method,
      headers,
      body,
      cache: "no-store",
    });

    const responseHeaders = new Headers();
    upstreamRes.headers.forEach((val, key) => {
      const lowerKey = key.toLowerCase();
      if (
        lowerKey !== "content-encoding" &&
        lowerKey !== "content-length" &&
        lowerKey !== "transfer-encoding"
      ) {
        responseHeaders.set(key, val);
      }
    });

    const resData = await upstreamRes.arrayBuffer();

    return new NextResponse(resData, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: responseHeaders,
    });
  } catch (err: any) {
    console.error(`[API Proxy Error] Failed to proxy to ${targetUrl}:`, err);
    return NextResponse.json(
      {
        detail: `Could not reach backend service at ${targetBase}. ${err?.message || err}`,
      },
      { status: 502 }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
export const PATCH = proxyRequest;
export const HEAD = proxyRequest;
