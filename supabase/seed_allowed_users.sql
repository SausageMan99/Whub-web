-- MVP: personnes autorisées à accéder au portail W hub CV Factory.
insert into public.allowed_users (email, role) values
  ('cdubosq@whub.fr', 'admin'),
  ('adavid@whub.fr', 'member'),
  ('ebronzini@wrecruiter.com', 'member'),
  ('mvassal@wrecruiter.com', 'member'),
  ('cpiaulet@whub.fr', 'member'),
  ('jpmaze@whub.fr', 'member'),
  ('nlesourd@whub.fr', 'member'),
  ('ccattiauxleconte@wrecruiter.com', 'member'),
  ('mfrappa@whub.fr', 'member'),
  ('lbronzini@whub.fr', 'member'),
  ('mdray@wrecruiter.com', 'member')
on conflict (email) do update set role = excluded.role;
