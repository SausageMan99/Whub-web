-- MVP: personnes autorisées à accéder au portail W hub CV Factory.
insert into public.allowed_users (email, role) values
  ('cdubosq@whub.fr', 'admin'),
  ('adavid@whub.fr', 'member'),
  ('ebronzini@wrecruiter.com', 'member'),
  ('mvassal@wrecruiter.com', 'member'),
  ('cpiaulet@whub.fr', 'member')
on conflict (email) do update set role = excluded.role;
