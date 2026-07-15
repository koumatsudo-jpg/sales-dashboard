/**
 * 内定率診断LP — リード収集用 Google Apps Script
 *
 * セットアップ手順(recruit-lp/README.md にも記載):
 * 1. リード蓄積用のGoogleスプレッドシートを新規作成
 * 2. 拡張機能 → Apps Script を開き、このファイルの内容を貼り付け
 * 3. NOTIFY_EMAIL を必要に応じて変更(空文字なら通知なし)
 * 4. デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *    - 実行するユーザー: 自分
 *    - アクセスできるユーザー: 全員
 * 5. 発行されたURLを index.html の CONFIG.GAS_ENDPOINT に設定
 */

const SHEET_NAME = "リード一覧";

// 新規リードが入ったら通知したいメールアドレス(不要なら "" のまま)
const NOTIFY_EMAIL = "";

const HEADERS = [
  "受信日時",
  "氏名",
  "大学・学部",
  "卒業年",
  "メール",
  "志望企業",
  "電話番号",
  "診断スコア(%)",
  "弱点TOP3",
  "Q1 学年",
  "Q2 志望業界",
  "Q3 志望企業レベル",
  "Q4 自己分析",
  "Q5 ガクチカ",
  "Q6 インターン経験",
  "Q7 ES",
  "Q8 面接",
  "Q9 企業研究",
  "Q10 行動量",
  "流入ページ",
  "リファラ",
];

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = getOrCreateSheet_();
    const a = data.answers || {};

    sheet.appendRow([
      new Date(),
      data.name || "",
      data.university || "",
      data.gradYear || "",
      data.email || "",
      data.targetCompany || "",
      // 先頭0落ち防止のため文字列として保存
      data.phone ? "'" + data.phone : "",
      data.score,
      data.weakest || "",
      a.grade || "",
      a.industry || "",
      a.companyLevel || "",
      a.selfAnalysis || "",
      a.gakuchika || "",
      a.internship || "",
      a.es || "",
      a.interview || "",
      a.research || "",
      a.action || "",
      data.page || "",
      data.referrer || "",
    ]);

    if (NOTIFY_EMAIL) {
      MailApp.sendEmail({
        to: NOTIFY_EMAIL,
        subject: `【内定率診断】新規リード: ${data.name}(${data.university})`,
        body: [
          `氏名: ${data.name}`,
          `大学: ${data.university}(${data.gradYear})`,
          `メール: ${data.email}`,
          `電話: ${data.phone || "-"}`,
          `志望企業: ${data.targetCompany || "-"}`,
          `診断スコア: ${data.score}%`,
          `弱点TOP3: ${data.weakest}`,
          "",
          `シート: ${SpreadsheetApp.getActiveSpreadsheet().getUrl()}`,
        ].join("\n"),
      });
    }

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold").setBackground("#eef2ff");
    sheet.setFrozenRows(1);
  }
  return sheet;
}
