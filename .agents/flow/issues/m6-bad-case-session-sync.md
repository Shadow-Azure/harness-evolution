# bad_cases 鏍逛細璇濊建杩瑰畾鏃跺悓姝?
[English](m6-bad-case-session-sync.en.md) | 涓枃

```yaml flow
kind: issue
id: m6-15
milestone: m6
depends:
  - m2-07
  - m4-01
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
  - docs/**
adr: []
github:
  number: 173
  url: https://github.com/Shadow-Azure/harness-evolution/issues/173
```

## 鑳屾櫙

`bad_cases.bad_case_session_id` 宸茬粡鎸囧悜闂鎵€灞炵殑鏍逛細璇濓紝浣嗘湰鏈嶅姟娌℃湁淇濊瘉杩欎簺鏍逛細璇濈殑鍘熷杞ㄨ抗杩涘叆 `trajectory_payloads`銆傚綋鍓嶈建杩瑰叆搴撳彧鏈夋湰鍦扮洰褰曞鍏ワ紙寮€鍙戠敤锛変笌绠＄悊鍛樻墜鍔?`POST /api/acquisition/pull` 涓ゆ潯璺緞锛涗袱鑰呴兘渚濊禆鎿嶄綔鑰呯煡閬?session id 鎴栨椂闂寸獥銆俠ad_cases 鎸佺画澧為暱鏃讹紝闂璇︽儏銆佹墽琛屾祦鍥惧拰鑷繘鍖栧惎鍔ㄩ兘鍙兘鍥犱负缂哄皯瀵瑰簲 payload 鑰岀湅涓嶅埌浼氳瘽銆?
鐜版湁涓婃父杞ㄨ抗濂戠害锛坄third_party_api/trajectory`锛変竴娆¤繑鍥炴暣妫?root package锛涙湰娆″鎺ョ殑鏌ヨ鏈嶅姟涓嶅悓锛氭帴鍙?1 鍙繑鍥炴煇涓?session锛堜富 agent 鎴?subagent锛夌洿鎺ヨЕ鍙戠殑瀛?sessionId锛屽繀椤婚€愬眰灞曞紑锛涙帴鍙?2 杩斿洖鍗曚釜 agent 鐨勮建杩癸紝涓旂姝㈠苟鍙戣皟鐢ㄣ€傚洜姝や笉鑳界洿鎺ュ鐢ㄧ幇鏈?pull 鐨勨€滀竴娆℃嬁鏁村寘鈥濇ā鍨嬶紝闇€瑕佹柊鐨勫鎴风涓庤皟搴﹁矾寰勩€?
## 鐩爣

- 鏂板瀹氭椂浠诲姟锛氫粠 `bad_cases` 鍙?distinct 鏍逛細璇?sessionId锛岀瓫鍑烘湭鍚屾鐨勬牴浼氳瘽锛岄€愪釜琛ラ綈涓?agent 涓庡叏閮?subagent 鐨勫師濮嬭建杩瑰埌 `trajectory_payloads`銆?- 杞ㄨ抗琛ラ綈鍚庡鐢ㄧ幇鏈夊綊涓€鍖?閲嶆斁绠＄嚎锛屼娇浼氳瘽銆丄gent 鏍戜笌闂璇绘ā鍨嬬珛鍗冲彲鏌ャ€?- 鏂板鏍逛細璇濆悓姝ョ姸鎬佽〃锛岃褰曟瘡涓?root 鐨勭姸鎬併€佸皾璇曟鏁般€佹渶鍚庨敊璇€丄gent 鏁颁笌瀹屾垚鏃堕棿锛屾敮鎸佸箓绛夐噸璺戜笌澶辫触閲嶈瘯銆?- 鏂板鍙缁熻鎺ュ彛涓庡叡浜绾︼細bad_cases 娑夊強鏍逛細璇濇€绘暟銆佸凡鍚屾鏁般€佹湭鍚屾鏁般€?- 鍓嶇灞曠ず涓婅堪缁熻锛屽苟鑳藉尯鍒嗘湭鍚屾銆佸悓姝ヤ腑涓庡け璐ャ€?- 瀹氭椂浠诲姟鍗曢锛涗笂涓€娆℃湭缁撴潫鏃朵笉寰楅噸澶嶅鐞嗗悓涓€鎵规牴浼氳瘽锛屽叿浣撹烦杩囥€佹帓闃熸垨鍚堝苟绛栫暐鍦ㄨ璁℃枃妗ｇ‘璁ゃ€?
## 璁捐渚濇嵁

- [04 搂5 鏁版嵁鎺ョ紳](../../../plans/fullstack-design/04-backend-architecture.md#L204-L214)锛氬師濮嬭建杩广€佸閮ㄨ〃涓?fixtures 鐨勮竟鐣屻€?- [05 搂4.8 鍘熷杞ㄨ抗鎺ュ叆](../../../plans/fullstack-design/05-api-design.md#L688-L708)锛歛cquisition 鐜版湁鎺ュ彛涓?job 璇箟銆?- [06 搂3.0 trajectory_payloads](../../../plans/fullstack-design/06-database-design.md#L105-L145)锛氬師濮?payload 鐨勫敮涓€瀛樺偍涓庡緟澶勭悊鍒ゅ畾銆?- [02 F9 杞ㄨ抗鎺ュ叆涓庡綊涓€鍖朷(../../../plans/fullstack-design/02-features.md)锛氳兘鍔涜竟鐣屼笌婕旂ず鏁版嵁瑙勫垯銆?- [11 bad_cases 鏍逛細璇濊建杩瑰畾鏃跺悓姝(../../../plans/fullstack-design/11-bad-case-session-sync.md)锛氱姸鎬佽〃銆佸閮ㄦ煡璇㈡湇鍔￠€傞厤銆侀亶鍘嗐€侀噸鍙犵瓥鐣ヤ笌鍓嶇缁熻銆?- 瀹炵幇鍐茬獊鏃朵互 11 绔犱负鍑嗐€?
## 瀹炵幇鍐呭

- 鏂板鏌ヨ鏈嶅姟瀹㈡埛绔細鎺ュ彛 1锛堢洿鎺ュ瓙 sessionId锛変笌鎺ュ彛 2锛堝崟 agent 杞ㄨ抗锛夛紝涓ユ牸鍝嶅簲妯″瀷銆佽秴鏃躲€侀噸璇曚笌閿欒鏄犲皠锛涙帴鍙?2 鍦ㄥ悓涓€杩涚▼鍐呬覆琛岃皟鐢ㄣ€?- 鏂板鏍逛細璇濊ˉ榻愭湇鍔★細鎸?`bad_cases` 鏍逛細璇濋€掑綊灞曞紑锛堜富 agent 鈫?鐩存帴瀛?鈫?瀛欙級锛屽幓閲嶅苟闃茬幆锛涙瘡涓?agent 鍙栬建杩瑰悗鍐欏叆 `trajectory_payloads`锛屾部鐢?`(root_session_id, agent_id)` 涓€琛屼竴涓?agent銆?- 鏂板瀹氭椂璋冨害涓?job kind锛氬鐢ㄧ幇鏈?scheduler 涓?`JobRunner` 妯″紡锛屽疄鐜板崟椋炰笌閲嶅彔澶勭悊锛涙壒娆″ぇ灏忋€侀噸璇曢樁姊笌鐘舵€佹祦杞湪璁捐鏂囨。瀹氱銆?- 鏂板鐘舵€佽〃涓?alembic 杩佺Щ锛氳嚦灏戝寘鍚?root_session_id銆佺姸鎬併€佸皾璇曟鏁般€佹渶鍚庨敊璇€乤gent 鏁般€佸悓姝ユ椂闂翠笌鏇存柊鏃堕棿锛宺oot_session_id 鍞竴銆?- 鏂板缁熻 API 涓庡叡浜绾︼細鎬绘暟銆佸凡鍚屾銆佹湭鍚屾锛涘墠绔睍绀哄姞杞姐€佺┖鎬佷笌澶辫触鎬併€?- 琛ュ厖娴嬭瘯锛氬灞傞亶鍘嗐€侀噸澶嶄笌鐜€佹帴鍙?2 涓茶绾︽潫銆佸崟椋炰笌閲嶅彔銆佸け璐ラ殧绂汇€佺姸鎬佸箓绛夈€佺粺璁?API 涓庡墠绔睍绀恒€?
## 瀹炴柦姝ラ

1. 浜у嚭璁捐鏂囨。涓庡師鍨嬩慨鏀圭偣锛岀‘璁ょ姸鎬佽〃銆丄PI 濂戠害銆侀噸鍙犵瓥鐣ヤ笌鍓嶇浣嶇疆锛屽苟鎻愪氦鎴浘纭銆?2. 濂戠害涓庢ā鍨嬶細鏌ヨ鏈嶅姟鍝嶅簲妯″瀷銆佺粺璁?DTO銆丱penAPI 涓庣敓鎴愮被鍨嬨€?3. 鏁版嵁搴擄細鐘舵€佽〃妯″瀷涓?alembic 杩佺Щ锛孲QLite/MySQL 鍙屽簱楠岃瘉銆?4. 瀹㈡埛绔笌閬嶅巻锛氭帴鍙?1 閫掑綊灞曞紑銆佹帴鍙?2 涓茶鎷夊彇銆乸ayload 鍐欏叆涓庡叡浜噸鏀俱€?5. 璋冨害涓庡崟椋烇細job kind銆佸畾鏃惰Е鍙戙€侀噸鍙犲鐞嗐€佸け璐ラ噸璇曚笌鐘舵€佹洿鏂般€?6. API 涓庡墠绔細缁熻鎺ュ彛銆侀〉闈㈠睍绀恒€佸姞杞?绌?澶辫触鎬佷笌鍒锋柊銆?7. 娴嬭瘯涓庨棬绂侊紱鐢?mock 鏌ヨ鏈嶅姟瀹屾垚鏈湴鍐掔儫銆?
## 渚濊禆涓庝氦浠樿竟鐣?
- 渚濊禆锛歮2-07锛堣皟搴︿笌 job 鍩虹璁炬柦锛夈€乵4-01锛堝閮ㄩ棶棰樿妯″瀷锛夈€?- 浜や粯杈圭晫锛氬彧琛ラ綈 bad_cases 鏍逛細璇濈殑杞ㄨ抗涓庣姸鎬?缁熻锛沚ad_cases 缁х画鎸夆€滃閮ㄥ啓鍚屽簱銆佹湰鏈嶅姟鍙鈥濆鐞嗭紱涓嶆敼鐜版湁鎵嬪姩 pull 鐨勫绾︿笌璇箟锛汣I 涓嶈皟鐢ㄧ湡瀹炴煡璇㈡湇鍔°€?
## 鐙珛楠岃瘉

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6 bad case sync"
pnpm verify:flow
pnpm lint:docs
```

- mock 鏌ヨ鏈嶅姟涓嬶紝缁欏畾 N 涓牴浼氳瘽鍙ˉ榻愪富/瀛?agent payload锛岀姸鎬佽鏁版纭€?- 涓婁竴娆′换鍔℃湭缁撴潫鏃跺啀娆¤Е鍙戜笉浼氫骇鐢熷苟鍙戞壒娆°€?- 鎺ュ彛 2 鐨勮皟鐢ㄥ簭鍒楁病鏈夐噸鍙犮€?- 鍓嶇缁熻涓庡悗绔竴鑷淬€?
## 楠屾敹鏍囧噯

- bad_cases 涓瘡涓湭鍚屾鏍逛細璇濇渶缁堥兘鏈夊畬鏁?main + subagent payload锛屽苟鑳藉綊涓€鍖栦负鍙 Session/Agent 鏍戙€?- 鐘舵€佽〃瀵瑰悓涓€鏍逛細璇濆箓绛夛紱澶辫触鍙噸璇曚笖閿欒鍙銆?- 瀹氭椂浠诲姟鍗曢锛岄噸鍙犳椂涓嶉噸澶嶆媺鍙栧悓涓€鎵规暟鎹€?- 鎺ュ彛 2 涓ユ牸涓茶銆?- 鍓嶇灞曠ず鎬绘暟銆佸凡鍚屾銆佹湭鍚屾锛屽埛鏂板悗涓庡悗绔竴鑷淬€?- 鐩稿叧闂ㄧ鍏ㄧ豢銆?
## 闂ㄧ涓?CI

- `pnpm test:api` / `pnpm test:db[:mysql]` / `pnpm test` / `pnpm typecheck:api`
- `pnpm test:web` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e`
- `pnpm contract:check` / `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 闈炵洰鏍?
- 涓嶆敼 bad_cases 鐨勭洿鎺ヨ搴撹竟鐣屼笌澶栭儴鍐欏叆鏂广€?- 涓嶆浛鎹㈡垨鍒犻櫎鐜版湁绠＄悊鍛樻墜鍔?pull锛涙湰 issue 鍙柊澧炶嚜鍔ㄨˉ榻愯矾寰勩€?- 涓嶅湪 CI 璁块棶鐪熷疄鏌ヨ鏈嶅姟锛涚湡瀹炶仈璋冭蛋鏈湴 mock 涓庡啋鐑熴€?- 涓嶅仛杞ㄨ抗鍐呭鍙樻洿妫€娴嬩笌鍏ㄩ噺閲嶆媺锛涙槸鍚︾撼鍏ュ閲忛噸鎷夌敱璁捐鏂囨。鏄庣‘銆?
