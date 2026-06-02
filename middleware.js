import { next } from '@vercel/edge';

export const config = { matcher: '/((?!favicon.ico).*)' };

export default function middleware(request) {
  const auth = request.headers.get('authorization');
  const expected = 'Basic ' + btoa(`${process.env.SITE_USER}:${process.env.SITE_PASS}`);

  if (auth === expected) {
    return next();
  }

  return new Response('Authentication required.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Protected"' },
  });
}
