-- Prepared only, NEVER executed by this package. Snapshot SHA256 789107035d2a800f68ca5ea45248a768d203b6a68d5c109e42a6d3aaf4f9f1ab.
-- Re-inventory and regenerate if any job/policy state changes. -v apply=true needs Lead GO.
\set ON_ERROR_STOP on
\if :{?apply}
\else
  \set apply false
\endif
\if :{?space_id}
\else
  \echo 'Required: -v space_id=<uuid>'
  \quit
\endif
begin isolation level serializable;

create temp table wm_pipeline_cutover_parameters(
  space_id uuid primary key,
  expected_revision bigint not null,
  expected_old_pipeline text not null,
  new_pipeline text not null,
  apply boolean not null,
  expected_automatic_from date not null,
  expected_budget_micro_usd bigint,
  job_ids text[] not null,
  expected_updated_at timestamptz[] not null
) on commit drop;

insert into wm_pipeline_cutover_parameters values (
  :'space_id'::uuid,
  221,
  'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:90c09c38fa788e6a',
  'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c',
  :'apply'::boolean,
  '2026-09-08',
  null,
  array[
    '08482dc018eb0f81a14c29144e563335d2d11450c4600e875c4c6fb2b04d1740',
    '08a7e17e63e1f214372c61fe83750a5a7f80ab74061bf8fa58ab9c9e56c4e0cf',
    '08d92f41ef69af3655173bd7eefd36e2bbbb23495ddc6f79a36bebf62e4071d8',
    '09413c6ef49c7aa5a757229a2b790aa1304f5bb6e46d8b662702722634f74a17',
    '0fb08484af8243241625875b553932647b306e75f8492481e0c7ad9f48dd06a2',
    '0fe2500eef6264dee77d962100decd38fba522f8b9361259b54a10b28948de57',
    '11918f50a1536e9407638f6cd64b3fa5aa95267e10dab3789dea36e297e68ca7',
    '153e79ed5a5ab429a558a94cbe7c1bc49fcb8a764816ff729fa5157f69199fbd',
    '153e8bf74cd9759b113e4c831bca7a972f3e2683004bf8a1f2e3f62b75173c1a',
    '186c1290471eedb1a0bea1ec64fe5dd6a8111cd34c7a247e18a1262ce850bc03',
    '221003af04d34f060a31aec7ee5514a48895f707e0bcffa0b7bd23d3c8a6a3af',
    '238680c65eefb3b712c07a309a937cf3b327237724d6829e3bedb1ca632a9d37',
    '2aaeaa4d7e20c91eefb03cc5c83694b3850202cb651d6ad8ad6f551cc2a57e63',
    '30544e1cbfb6df5f23f16f99907976a582245da39f48fe41e2415473108c979c',
    '332009f247a28ae5bc2acc84f07fe79d119101c258edc057288f476ecd5bfa8b',
    '334b46ab70143630136fc0a3cfc6732682a54e46b537b152968988e4c5fc2e88',
    '3d12b0e54a91eb702413a00a83263df0c91a4913ff26cf5e92e04ecd099e4167',
    '44177b32670955932eb49e76dd7afc36abb2bdcc798e0b84a98bf4c09dade5cc',
    '45c58eb96185272ab8119136182a9d6192ef6f81c1b113503525e11a5886c017',
    '476dd6ddb2a97a8032905e1b49e225a42703bf7e4a63707509b9f30a0c4047cf',
    '4ef5dd7705f140991c6d828869900b164f1eb3af16d396cbe4743e91fa75b6ea',
    '59ae27fff2d56070a34e0b2e0642e3a595810f073d628bfa5f0fc529d6484618',
    '5e6dfd23b0ac50026b4811d9c765c5011106e6c211eaac123ab5b50f9cba3741',
    '5ea282a3d90cf27497c2d037ae618d4c7881b031fd9c0a3c351a26cfb6ca0ad5',
    '5ee3bf87cc1909e31ffb97f88576b4470d1b537b690191907c116cbc23922fc0',
    '60d0cb00e7eb92de8b42d358c9e25d55483546eac95ca74af5570d8683296210',
    '638960a4f3d479c55ceb368b73d4d56b29a2ca8858d20f66c7c4e67e98524693',
    '66e666e51fab7ac091f7b99ab985eb8b2dffe72e5a4642d166f639cf00c13656',
    '686877a8a5098ccf294846bdc5e5f4c41a6b4a057d8834d5d7eb47ab2a5bdde8',
    '698c9aa09305379257913673f97b14c46c70d2870c3753e6af70f6ec43d97965',
    '6ce150e26d29285ce2cd013bd68ca54dc27c97d21bd0a233627822435fbc78c5',
    '714d53f42befeb06745a4798947cf664c7677f0176552e7865001714bc49534e',
    '75173f1edfb7d1cfd70e5683f02842697adb496dd2086b30625b0c332b73ab83',
    '7c5ac465b605653c66a2a53536c5ccc5377ce68cd9fad7c694db8101fdb62f2f',
    '7caf981215590ac3a75d8c27a0d079dd0b772f199dfa0b104ccfbc2bd1478132',
    '81ea3be3af240a606141627e4946566618446c4e77a4a4b2a899f8efe454b97d',
    '86149a5e2417499e08f277b80ee0247bfc875ff95712b149914cfd7b2d89e8a7',
    '91a2a903fe396e43f7297671bcb16852179b838242e2c733a8f4348357a100d8',
    '984236464d157676dec4fab70e7d24e6894cf44d97de56f14af0b82f471674b4',
    '9db6eb68e9fc5e8e1a54147a3c5c668ab9734ca0b2e3b8f555a4114da8313549',
    'a1250c093ef1d3f9c8ed88e2565535e7056260e5ee43a5037e7ff7155183a493',
    'acc34319aae06f2bb1172aca052bdd01a4d18687472410acc41416fd3dfeb623',
    'b1a3973363d11967b0fb223279f934e188f362c486ec2b95b6bbdd9da70e3aba',
    'b24f3d3ad3b133f88e213416da6efc9721be954bcde9d534f07f5144aab10b95',
    'b646e5ea710df7286553a751649b468b6d76d6e8e198a1697bc3ce25886f92e5',
    'b7f61520fa39e337628b4ab8343a39ca80bec4fec23882ffe72c156ca1db7466',
    'bcc49102568ba3d61f40a9b8159af468001d16c3febcc4700dd434d32898745a',
    'beeb3215f7f3aa10041176b07070cce81176b031e816a767030a540584ece8f7',
    'cb9ca848355944ef7ef78e7afb09abbd2c90f2a08b163a8e824c9522eb5fb06b',
    'ce71f5e33f569c3d34d2489284d50696c3b8cf1da481e56ab989c2a6e05b87cc',
    'd00eff3efb0bfac7415f1232d78a97702dac2eb009c04c55e30b39d8de76dd6f',
    'd825f68c2092b9ed5372652ca5866205da64c6ef64730e1908f80b0319a9c228',
    'dc7175f9524e2f107f131e0b499c052db429dd000c6b59b257a5a112cd5ab148',
    'dcf884e7fbe278fb2d70bc139c1e8caf319e2d65018270708bf790ef7e17e736',
    'ddbe693b4530bd874c6e2776b2936ba61e45444dc7e6f934bb4533c89572b395',
    'e64cd76077484fa37c25db66ec5695e41e6c6e2f2478b1be0632cd8b8675df8f',
    'ebd86b2181c2aa3a0f207bf76eae5c8081599c3908d6eb9df410043396eb6959',
    'ed1047a431f13b67a2a161fc7293604c7fc5dc3c553eb2862e2bc677fbe49ae8',
    'eda621b3698ca059bf971fd69a8a04fdf712d3e819f96c74c56f83bc3c9595ad',
    'efeee11fc9a5270bbba6255dccca4a3c500f8ef16bbb0f77ccd7a8ead3cbe299',
    'f91105a33dc99b071c2e380e15216856e6af9b6e8e46c5f1aede070b33b181e8',
    'f919da3ccb93a6c9d24d7022edf9050ff3cc0575ff232b12c6d671058581a754',
    'fa6075684b2c591eccb64ea65fe0f76b0232c9066ddde7d743dad74360250e75'
  ],
  array[
    '2026-10-02T10:20:16.516316+00:00'::timestamptz,
    '2026-09-25T09:40:16.596374+00:00'::timestamptz,
    '2026-10-02T08:20:16.9629+00:00'::timestamptz,
    '2026-10-05T12:50:15.897988+00:00'::timestamptz,
    '2026-09-30T09:30:17.967645+00:00'::timestamptz,
    '2026-10-01T11:20:16.910148+00:00'::timestamptz,
    '2026-10-02T12:20:16.865017+00:00'::timestamptz,
    '2026-10-05T08:30:16.340028+00:00'::timestamptz,
    '2026-09-29T08:40:16.780384+00:00'::timestamptz,
    '2026-10-05T09:50:15.75494+00:00'::timestamptz,
    '2026-10-01T14:10:17.196706+00:00'::timestamptz,
    '2026-10-05T12:30:15.769081+00:00'::timestamptz,
    '2026-10-01T09:20:16.664383+00:00'::timestamptz,
    '2026-09-29T09:30:16.573824+00:00'::timestamptz,
    '2026-10-02T10:30:16.818269+00:00'::timestamptz,
    '2026-10-01T14:30:17.375737+00:00'::timestamptz,
    '2026-09-28T11:40:17.150033+00:00'::timestamptz,
    '2026-10-02T08:20:17.009419+00:00'::timestamptz,
    '2026-09-28T12:10:16.810151+00:00'::timestamptz,
    '2026-10-05T10:10:15.78113+00:00'::timestamptz,
    '2026-10-05T07:50:15.924985+00:00'::timestamptz,
    '2026-09-30T11:00:16.814465+00:00'::timestamptz,
    '2026-10-05T09:00:17.099448+00:00'::timestamptz,
    '2026-09-29T09:40:16.955743+00:00'::timestamptz,
    '2026-09-30T15:20:16.827833+00:00'::timestamptz,
    '2026-09-25T09:50:16.62363+00:00'::timestamptz,
    '2026-10-02T13:30:17.235813+00:00'::timestamptz,
    '2026-10-01T12:00:17.020793+00:00'::timestamptz,
    '2026-09-29T10:30:16.676018+00:00'::timestamptz,
    '2026-09-30T15:10:16.872752+00:00'::timestamptz,
    '2026-10-02T12:40:16.624978+00:00'::timestamptz,
    '2026-09-28T12:40:16.709399+00:00'::timestamptz,
    '2026-10-01T07:00:16.69362+00:00'::timestamptz,
    '2026-09-29T08:10:16.717051+00:00'::timestamptz,
    '2026-10-01T09:10:16.56525+00:00'::timestamptz,
    '2026-09-25T08:40:16.702442+00:00'::timestamptz,
    '2026-09-29T14:30:16.970776+00:00'::timestamptz,
    '2026-09-28T10:20:16.941163+00:00'::timestamptz,
    '2026-09-28T08:50:16.522597+00:00'::timestamptz,
    '2026-09-24T11:50:16.562477+00:00'::timestamptz,
    '2026-09-28T08:20:17.256252+00:00'::timestamptz,
    '2026-10-05T17:20:15.739596+00:00'::timestamptz,
    '2026-09-29T13:30:17.132685+00:00'::timestamptz,
    '2026-09-25T10:30:17.957506+00:00'::timestamptz,
    '2026-09-23T11:30:17.000122+00:00'::timestamptz,
    '2026-09-30T09:40:17.043856+00:00'::timestamptz,
    '2026-09-28T11:50:16.427787+00:00'::timestamptz,
    '2026-10-01T10:10:17.024591+00:00'::timestamptz,
    '2026-10-01T08:10:18.021016+00:00'::timestamptz,
    '2026-09-24T09:00:16.796933+00:00'::timestamptz,
    '2026-10-01T11:20:16.827461+00:00'::timestamptz,
    '2026-10-05T12:10:15.866326+00:00'::timestamptz,
    '2026-09-23T11:50:16.937712+00:00'::timestamptz,
    '2026-09-28T14:00:16.762039+00:00'::timestamptz,
    '2026-10-05T09:40:15.889918+00:00'::timestamptz,
    '2026-10-01T07:30:16.543167+00:00'::timestamptz,
    '2026-10-02T08:40:16.493153+00:00'::timestamptz,
    '2026-09-25T11:50:16.765352+00:00'::timestamptz,
    '2026-09-29T09:20:16.848197+00:00'::timestamptz,
    '2026-10-02T07:10:16.495709+00:00'::timestamptz,
    '2026-10-05T12:50:15.879605+00:00'::timestamptz,
    '2026-10-05T08:20:16.041259+00:00'::timestamptz,
    '2026-10-02T12:10:17.006251+00:00'::timestamptz
  ]
);

create temp table wm_pipeline_cutover_result(result jsonb not null) on commit drop;

do $$
declare
  p wm_pipeline_cutover_parameters%rowtype;
  s public.wm_spaces%rowtype;
  c public.wm_processing_config%rowtype;
  j public.wm_jobs%rowtype;
  prior jsonb;
  request jsonb;
  outcome jsonb;
  reason text;
  command_hex text;
  command_id uuid;
  ordinal integer;
begin
  select * into strict p from wm_pipeline_cutover_parameters;
  if p.space_id is distinct from '96a2dc44-9b9e-4644-b236-c5c1956cd39d'::uuid then
    raise exception 'Unexpected space' using errcode='22023';
  end if;
  if p.new_pipeline = p.expected_old_pipeline
     or p.new_pipeline !~ '^v11:compact1:gate1:gpt-5[.]6-terra:[0-9a-f]{16}:canonical1:[0-9a-f]{16}$' then
    raise exception 'Final runtime pipeline is missing or malformed' using errcode='22023';
  end if;

  select * into s from public.wm_spaces where id=p.space_id for update;
  if not found or s.state='retired' or s.owner_id is null or s.revision is distinct from p.expected_revision then
    raise exception 'Space owner/state/revision changed' using errcode='40001';
  end if;
  select * into c from public.wm_processing_config where space_id=p.space_id for update;
  if not found or not c.enabled or c.automatic_from is distinct from p.expected_automatic_from
     or c.budget_micro_usd is distinct from p.expected_budget_micro_usd
     or c.pipeline is distinct from p.expected_old_pipeline then
    raise exception 'Processing policy changed' using errcode='40001';
  end if;

  -- wm_claim_job and wm_enqueue lock wm_spaces first, so this lock makes the
  -- complete validation/update/audit block atomic with worker and intake.
  perform 1 from public.wm_jobs
   where space_id=p.space_id and id=any(p.job_ids)
   order by id for update;
  if (select array_agg(id order by id) from public.wm_jobs
      where space_id=p.space_id and state='queued') is distinct from p.job_ids then
    raise exception 'Pending queue membership changed' using errcode='40001';
  end if;
  if (select count(*) from public.wm_jobs j0
      where j0.space_id=p.space_id and j0.id=any(p.job_ids)
        and j0.state='queued' and j0.reason is null and j0.pipeline=p.expected_old_pipeline
        and j0.expected_revision is null and j0.prepared_payload is null
        and j0.lease_token is null and j0.lease_until is null and j0.attempts=0
        and j0.applied_revision is null
        and j0.updated_at=p.expected_updated_at[array_position(p.job_ids,j0.id)]) = 63
     and not exists(select 1 from public.wm_model_calls m where m.space_id=p.space_id and m.job_id=any(p.job_ids)) then
    null;
  else
    raise exception 'An unstarted target job changed' using errcode='40001';
  end if;
  if (select count(*) from public.wm_jobs where space_id=p.space_id and state='applied') != 104
     or (select count(*) from public.wm_jobs where space_id=p.space_id and state='review'
           and id='a34706df2728e22f1c0b7648cac2a06402982a708df669d5d90fec6eb7c246f5') != 1
     or (select count(*) from public.wm_jobs where space_id=p.space_id and state='review') != 1
     or (select count(*) from public.wm_model_calls where space_id=p.space_id) != 1447 then
    raise exception 'Paid, applied or review history changed' using errcode='40001';
  end if;
  if not exists(select 1 from pg_catalog.pg_constraint k
      where k.conrelid='public.wm_job_decisions'::regclass and k.conname='wm_job_decisions_action_check'
        and pg_catalog.pg_get_constraintdef(k.oid) like '%pipeline_cutover%') then
    raise exception 'Pipeline cutover audit migration is not installed' using errcode='55000';
  end if;

  update public.wm_processing_config set pipeline=p.new_pipeline where space_id=p.space_id;
  reason:=format('Technischer Cutover von %s auf den geprüften Runtime-Stand %s; ausschließlich 63 inventarisierte unverarbeitete Queue-Jobs ohne Calls, Prepared-Payload, Lease oder Kontextbindung werden neu gebunden. Startdatum und unbegrenztes Budget bleiben unverändert.',p.expected_old_pipeline,p.new_pipeline);

  for j in select * from public.wm_jobs where space_id=p.space_id and id=any(p.job_ids) order by id for update loop
    prior:=to_jsonb(j);
    ordinal:=array_position(p.job_ids,j.id);
    command_hex:=encode(extensions.digest(convert_to(p.space_id::text||':pipeline-cutover:'||p.new_pipeline||':'||j.id,'UTF8'),'sha256'),'hex');
    command_id:=(substr(command_hex,1,8)||'-'||substr(command_hex,9,4)||'-'||substr(command_hex,13,4)||'-'||
                 substr(command_hex,17,4)||'-'||substr(command_hex,21,12))::uuid;
    request:=jsonb_build_object(
      'operation','pipeline_cutover','actor_id',s.owner_id,'job_id',j.id,
      'expected_revision',p.expected_revision,'expected_updated_at',p.expected_updated_at[ordinal],
      'expected_old_pipeline',p.expected_old_pipeline,'new_pipeline',p.new_pipeline,
      'expected_policy',jsonb_build_object('enabled',true,'automatic_from',p.expected_automatic_from,
        'budget_micro_usd',p.expected_budget_micro_usd),
      'expected_job',jsonb_build_object('state','queued','reason',null,'calls',0,'prepared',false,
        'expected_revision',null,'leased',false,'attempts',0,'applied_revision',null));
    update public.wm_jobs set pipeline=p.new_pipeline,updated_at=clock_timestamp()
      where space_id=p.space_id and id=j.id;
    select jsonb_build_object('job_id',id,'state',state,'pipeline',pipeline,'updated_at',updated_at,
      'revision',s.revision) into outcome from public.wm_jobs where space_id=p.space_id and id=j.id;
    insert into public.wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result)
      values(p.space_id,command_id,j.id,s.owner_id,'pipeline_cutover',reason,request,prior,outcome);
  end loop;

  if (select (to_jsonb(c1)-'pipeline'-'updated_at') is not distinct from (to_jsonb(c)-'pipeline'-'updated_at')
      from public.wm_processing_config c1 where c1.space_id=p.space_id) is not true then
    raise exception 'Cutover changed processing policy beyond pipeline' using errcode='40001';
  end if;
  if (select count(*) from public.wm_jobs where space_id=p.space_id and id=any(p.job_ids)
      and state='queued' and pipeline=p.new_pipeline and expected_revision is null
      and prepared_payload is null and lease_token is null and lease_until is null and attempts=0) != 63 then
    raise exception 'Cutover postcondition failed' using errcode='40001';
  end if;
  insert into wm_pipeline_cutover_result values(jsonb_build_object(
    'mode',case when p.apply then 'apply' else 'dry_run' end,
    'revision',s.revision,'old_pipeline',p.expected_old_pipeline,'new_pipeline',p.new_pipeline,
    'automatic_from',p.expected_automatic_from,'budget_micro_usd',p.expected_budget_micro_usd,
    'jobs',p.job_ids,'audit_rows',63));
end $$;

table wm_pipeline_cutover_result;

\if :apply
  commit;
\else
  rollback;
\endif
