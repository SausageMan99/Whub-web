-- MVP: remplace ces emails par les 4-5 personnes W hub autorisées.
insert into public.allowed_users (email, role) values
  ('clement.dubosq@whub.fr', 'admin'),
  ('collegue1@whub.fr', 'member'),
  ('collegue2@whub.fr', 'member'),
  ('collegue3@whub.fr', 'member'),
  ('collegue4@whub.fr', 'member')
on conflict (email) do update set role = excluded.role;
