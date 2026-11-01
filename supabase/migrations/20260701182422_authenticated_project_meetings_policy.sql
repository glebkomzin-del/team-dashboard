CREATE POLICY "authenticated_all_project_meetings"
  ON public.project_meetings
  FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);
