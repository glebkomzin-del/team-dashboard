-- Document the only intended reader explicitly; browser roles remain denied.
create policy wm_service_token_reader on memory_private.service_tokens
for select to service_role using (true);
