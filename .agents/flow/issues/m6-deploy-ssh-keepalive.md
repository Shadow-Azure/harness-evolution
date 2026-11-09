# Deploy 娴佹按绾?SSH 浼氳瘽淇濇椿

[English](m6-deploy-ssh-keepalive.en.md) | 涓枃

```yaml flow
kind: issue
id: m6-23
milestone: m6
depends:
  - m6-22
priority: P1
status: ready
scope:
  - .github/workflows/**
  - .agents/flow/**
adr: []
github:
  number: 202
  url: https://github.com/Shadow-Azure/harness-evolution/issues/202
```

## 鑳屾櫙

m6-22 浜や粯鐨勯娆＄湡瀹炲彂甯冧腑锛岃繙绋?pip 瀹夎鏈熼棿 SSH 浼氳瘽琚綉缁滀腑闂磋澶囬噸缃紙`Connection reset by peer`锛宔xit 255锛夛紝Deploy 闅忎箣澶辫触銆傛湇鍔″櫒渚у凡鏀圭敤闃块噷浜?pip 闀滃儚缂╃煭楗卞拰绐楀彛锛屼絾闀胯€楁椂杩滅▼姝ラ锛堣縼绉汇€佸ぇ浣撶Н涓婁紶锛変粛渚濊禆榛樿鏃犱繚娲荤殑 SSH 杩炴帴锛屼换浣曚竴娆＄綉缁滄姈鍔ㄩ兘浼氳鏁存潯鍙戝竷浣滃簾銆?
## 鐩爣

- Deploy workflow 鐨勪袱澶?SSH锛坮sync 涓婁紶涓庤繙绋嬪彂甯冭剼鏈級甯?`ServerAliveInterval=30` / `ServerAliveCountMax=6`锛岀┖闂叉湡涓诲姩淇濇椿锛岃繛鎺ユ姈鍔ㄥ彲鑷剤銆?
## 璁捐渚濇嵁

- [plans/fullstack-design/01-architecture.md 搂6 閮ㄧ讲褰㈡€佷笌鎵╁睍璺緞](../../../plans/fullstack-design/01-architecture.md)锛氬崟瀹炰緥 SaaS 浜や粯閫氶亾鐨勫彲闈犳€у睘浜庤褰㈡€佺殑杩愯瑕佹眰锛涙湰 issue 鍙姞鍥洪€氶亾锛屼笉鏀瑰彉閮ㄧ讲璇箟銆?- m6-22 issue 鐨勫疄鐜板唴瀹癸紙Deploy workflow 涓?release.sh 鑱岃矗鍒掑垎锛変负鏈?issue 鐨勭洿鎺ュ墠缃€?
## 瀹炵幇鍐呭

- `.github/workflows/deploy.yml`锛歚SSH_CMD` 涓庡彂甯冩楠ょ殑 ssh 鍛戒护杩藉姞涓や釜 keepalive 鍙傛暟銆?
## 瀹炴柦姝ラ

1. 鍦?m6-22 浜や粯鍚庣殑缂洪櫡淇 PR 涓慨鏀?`deploy.yml` 骞跺悓 PR 鍐呮帹杩涙湰 issue 鑷?ready銆?2. 鐢卞悎骞跺悗鐨?Deploy run 楠岃瘉鐪熷疄鍙戝竷閾捐矾銆?
## 渚濊禆涓庝氦浠樿竟鐣?
- 渚濊禆锛歮6-22锛圖eploy workflow 鏈綋锛夈€?- 浜や粯杈圭晫锛氬彧鏀?workflow 鐨?ssh 鍙傛暟锛涗笉鍔ㄥ彂甯冭剼鏈笌鏈嶅姟鍣ㄩ厤缃€?- 闈炵洰鏍囷細瑙佷笅鏂逛笓鑺傘€?
## 鐙珛楠岃瘉

```sh
pnpm verify:flow
```

- `verify:flow` 鍏ㄩ儴閫氳繃锛涘悎骞跺悗鐨?Deploy run 鍏ㄧ豢涓旀湇鍔″櫒 `/api/health` 杩斿洖 200銆?
## 楠屾敹鏍囧噯

- Deploy workflow 鐨?ssh 鍛戒护鍚繚娲诲弬鏁般€?- 鍚堝苟鍚庣殑鑷姩鍙戝竷鍏ㄧ豢锛屽仴搴锋鏌ラ€氳繃銆?
## 闂ㄧ涓?CI

- `verify:flow --diff`锛氭爣棰樺甫 `(#N)`锛宒iff 钀藉湪鐧昏 scope 鍐呫€?- 鏈?issue 鐢辩己闄蜂慨澶?PR 鍦ㄥ悓 PR 鍐呬粠 backlog 婵€娲伙紙flow README 鍏佽鐨勫悎娉曡矾寰勶級銆?
## 闈炵洰鏍?
- 涓嶆敼 rsync 鎺掗櫎瑙勫垯銆佽Е鍙戞潯浠朵笌鍙戝竷鑴氭湰銆?- 涓嶅紩鍏ョ涓夋柟 Actions銆?