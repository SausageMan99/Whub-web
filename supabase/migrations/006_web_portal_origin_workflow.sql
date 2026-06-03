alter table public.cv_requests
  add column if not exists origin text not null default 'web_portal';

alter table public.cv_requests
  add column if not exists workflow text not null default 'telegram_whub_cv_generation';
