create schema if not exists auth;

create table if not exists auth.users (
  id uuid primary key
);

do $$
begin
  create role anon nologin;
exception when duplicate_object then
  null;
end
$$;

do $$
begin
  create role authenticated nologin;
exception when duplicate_object then
  null;
end
$$;
