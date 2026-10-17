/**
 * frontend/static/components/sports-intelligence.js
 * ─────────────────────────────────────────────────────────────────
 * Sports Intelligence & 10-Discipline Rule Classifier
 *
 * Responsibilities:
 * - 10 Sports discipline classification heuristics (UCL, Thai Football,
 *   Badminton, ONE Championship/Boxing, Volleyball, Tennis, Golf,
 *   Motorsport/F1, Para Games, Other Sports)
 * - Match content type classification (result, schedule, general news)
 * - Sports cluster and domain detection heuristics
 * ─────────────────────────────────────────────────────────────────
 */

export const SPORTS_DISCIPLINES = [
  { id: "all", label: "ทั้งหมด", icon: "sports" },
  { id: "football_europe", label: "ฟุตบอลยุโรป & UCL", icon: "sports_soccer" },
  { id: "football_thai", label: "ฟุตบอลไทย & ช้างศึก", icon: "sports_soccer" },
  { id: "badminton", label: "แบดมินตัน & ขนไก่", icon: "sports_tennis" },
  { id: "boxing", label: "มวย & ONE ลุมพินี", icon: "sports_mma" },
  { id: "volleyball", label: "วอลเลย์บอล & ลูกยาง", icon: "sports_volleyball" },
  { id: "tennis", label: "เทนนิส", icon: "sports_tennis" },
  { id: "golf", label: "กอล์ฟ", icon: "sports_golf" },
  { id: "motorsport", label: "มอเตอร์สปอร์ต & F1", icon: "sports_motorsports" },
  { id: "paragames", label: "พาราเกมส์", icon: "accessible_forward" },
  { id: "other_sports", label: "กีฬาอื่นๆ", icon: "fitness_center" },
];

export function classifySportsArticle(art) {
  if (!art) {
    return {
      discipline: "other_sports",
      disciplineLabel: "กีฬาอื่นๆ",
      leagueBadge: "🏃 กีฬาอื่นๆ",
      leagueBadgeClass: "bg-slate-800 text-slate-200 border border-slate-700/50",
      contentType: "general",
      contentTypeLabel: "ข่าวทั่วไป",
      isResult: false,
      scoreHighlight: "",
    };
  }

  const title = String(art.title ?? "").toLowerCase();
  const summary = String(art.summary ?? "").toLowerCase();
  const url = String(art.url ?? "").toLowerCase();
  const text = `${title} ${summary} ${url}`;

  let discipline = "other_sports";
  let disciplineLabel = "กีฬาอื่นๆ";
  let leagueBadge = "🏃 กีฬาอื่นๆ";
  let leagueBadgeClass = "bg-slate-700 text-slate-100";

  // 1. Check Football Europe & International (including English clubs)
  if (/ucl|แชมเปี้ยนส์ ลีก|แชมเปียนส์ ลีก|ชปล|พรีเมียร์ลีก|premier league|ยูโรปา|europa|ลาลีกา|la liga|บุนเดสลีกา|bundesliga|กัลโช่|serie a|แมนฯ ซิตี้|แมนซิตี้|manchester city|เปแอสเช|psg|แมนยู|แมนฯ ยูไนเต็ด|manchester united|ลิเวอร์พูล|liverpool|อาร์เซน่อล|อาร์เซนอล|arsenal|เชลซี|chelsea|สเปอร์ส|tottenham|มาดริด|แอต\.มาดริด|real madrid|บาร์เซโลน่า|barcelona|บาเยิร์น|bayern|ดอร์ทมุนด์|dortmund|ลินซ์|ลีลล์|คริสตัล พาเลซ|ลียง|โคโม|เฟเยนูร์ด|ลูกหนังยุโรป|เรอัล มาดริด|อินเตอร์|inter milan|ยูเวนตุส|juventus|มิลาน|ac milan|วาร์ดี|เบิร์นลีย์/i.test(text)) {
    discipline = "football_europe";
    disciplineLabel = "ฟุตบอลยุโรป & สากล";
    if (/ucl|แชมเปี้ยนส์ ลีก|แชมเปียนส์ ลีก|ชปล/i.test(text)) {
      leagueBadge = "⚽ UCL";
      leagueBadgeClass = "bg-indigo-900 text-indigo-100 border border-indigo-700/50";
    } else if (/พรีเมียร์ลีก|premier league/i.test(text)) {
      leagueBadge = "⚽ พรีเมียร์ลีก";
      leagueBadgeClass = "bg-purple-900 text-purple-100 border border-purple-700/50";
    } else if (/ยูโรปา|europa/i.test(text)) {
      leagueBadge = "⚽ ยูโรปาลีก";
      leagueBadgeClass = "bg-amber-900 text-amber-100 border border-amber-700/50";
    } else {
      leagueBadge = "⚽ ฟุตบอลยุโรป";
      leagueBadgeClass = "bg-blue-900 text-blue-100 border border-blue-700/50";
    }
  }
  // 2. Check Badminton (checked before generic ทีมชาติไทย)
  else if (/แบดมินตัน|badminton|วิว กุลวุฒิ|กุลวุฒิ|เมย์ รัชนก|รัชนก|บาส-ปอป้อ|บาส ปอป้อ|เดชาพล|ทรัพย์สิรี|ขนไก่|แบดไทย|โยเน็กซ์|yonex|bwf|คุณหญิงปัทมา/i.test(text)) {
    discipline = "badminton";
    disciplineLabel = "แบดมินตัน";
    leagueBadge = "🏸 แบดมินตัน";
    leagueBadgeClass = "bg-teal-900 text-teal-100 border border-teal-700/50";
  }
  // 3. Check Volleyball (checked before generic ทีมชาติไทย)
  else if (/วอลเลย์|ลูกยาง|pmyc|วอลเลย์บอล|volleyball|vnl/i.test(text)) {
    discipline = "volleyball";
    disciplineLabel = "วอลเลย์บอล & กีฬาในร่ม";
    if (/ชายหาด/i.test(text)) {
      leagueBadge = "🏐 วอลเลย์ชายหาด";
    } else {
      leagueBadge = "🏐 ลูกยาง / PMYC";
    }
    leagueBadgeClass = "bg-amber-800 text-amber-100 border border-amber-600/50";
  }
  // 4. Check Boxing & Martial Arts
  else if (/มวย|boxing|วัน แชมเปียนชิพ|one championship|one ลุมพินี|oneลุมพินี|one lumpinee|มวยไทย|ไทยไฟต์|ศึกจ้าวมวยไทย|เวทีมวย|มวยสากล|กำปั้น|ไฟต์|น็อกเอาต์|ชั่งน้ำหนัก|ตะวันฉาย|รถถัง|ซุปเปอร์บอน|ไฟท์|คิกบ็อกซิ่ง|mma|ufc|ศิลปะการต่อสู้|สังเวียน/i.test(text)) {
    discipline = "boxing";
    disciplineLabel = "มวย & ศิลปะการต่อสู้";
    if (/one championship|วัน แชมเปียนชิพ|one ลุมพินี|oneลุมพินี/i.test(text)) {
      leagueBadge = "🥊 ONE Championship";
    } else if (/มวยไทย/i.test(text)) {
      leagueBadge = "🥊 มวยไทย";
    } else if (/ufc|mma/i.test(text)) {
      leagueBadge = "🥊 UFC / MMA";
    } else {
      leagueBadge = "🥊 มวย";
    }
    leagueBadgeClass = "bg-red-950 text-red-200 border border-red-800/50";
  }
  // 5. Check Tennis
  else if (/เทนนิส|tennis|วิมเบิลดัน|wimbledon|ยูเอส โอเพ่น|us open|เฟรนช์ โอเพ่น|french open|ออสเตรเลียน โอเพ่น|australian open|atp|wta|นาดาล|ยอโควิช|อัลคาราซ|ซินเนอร์|โมนาสตีร์/i.test(text)) {
    discipline = "tennis";
    disciplineLabel = "เทนนิส";
    leagueBadge = "🎾 เทนนิส";
    leagueBadgeClass = "bg-lime-900 text-lime-100 border border-lime-700/50";
  }
  // 6. Check Golf
  else if (/กอล์ฟ|golf|พีจีเอ|pga|แอลพีจีเอ|lpga|โปรเม|โปรจีน|ลิเดีย โค|ทีออฟ|พัตต์|เบอร์ดี้|ฮอนด้า แอลพีจีเอ/i.test(text)) {
    discipline = "golf";
    disciplineLabel = "กอล์ฟ";
    leagueBadge = "⛳ กอล์ฟ";
    leagueBadgeClass = "bg-emerald-950 text-emerald-200 border border-emerald-800/50";
  }
  // 7. Check Motorsport
  else if (/โมโตจีพี|motogp|f1|formula 1|ฟอร์มูล่าวัน|สมเกียรติ จันทรา|กรังด์ปรีซ์|มอเตอร์สปอร์ต|motorsport|อัลบอน|albon/i.test(text)) {
    discipline = "motorsport";
    disciplineLabel = "มอเตอร์สปอร์ต";
    if (/f1|formula 1|ฟอร์มูล่าวัน|อัลบอน/i.test(text)) {
      leagueBadge = "🏎️ F1 / กรังด์ปรีซ์";
    } else if (/โมโตจีพี|motogp|สมเกียรติ/i.test(text)) {
      leagueBadge = "🏍️ โมโตจีพี";
    } else {
      leagueBadge = "🏎️ มอเตอร์สปอร์ต";
    }
    leagueBadgeClass = "bg-cyan-950 text-cyan-200 border border-cyan-800/50";
  }
  // 8. Check Para Games
  else if (/พาราเกมส์|paragames|คนพิการ|เอเชี่ยนพาราเกมส์|พาราลิมปิก|paralympic|วีลแชร์/i.test(text)) {
    discipline = "paragames";
    disciplineLabel = "พาราเกมส์ & คนพิการ";
    leagueBadge = "♿ เอเชี่ยนพาราเกมส์";
    leagueBadgeClass = "bg-emerald-900 text-emerald-100 border border-emerald-700/50";
  }
  // 9. Check Thai Football & Asian Club
  else if (/ไทยลีก|ไทยพรีเมียร์ลีก|ช้างศึก|ทีมชาติไทย|เอเชียน คัพ|เอเชี่ยนคัพ|asian cup|คิงส์คัพ|ท่าเรือ|การท่าเรือ|บีจี ปทุม|จามจุรี|คาชิว่า|คาชิวะ|acl|เอเอฟซี|แอดิเลด|บอลนักเรียน|ฟุตบอลนักเรียน|กรมพลศึกษา|ไทย วีเมนส์ ลีก|ฟุตซอล|ฟุตบอลไทย|บอลไทย|ชบาแก้ว/i.test(text)) {
    discipline = "football_thai";
    disciplineLabel = "ฟุตบอลไทย & บอลเอเชีย";
    if (/ไทยลีก 3/i.test(text)) {
      leagueBadge = "🇹🇭 ไทยลีก 3";
    } else if (/ไทยลีก/i.test(text)) {
      leagueBadge = "🇹🇭 ไทยลีก";
    } else if (/เอเชียน คัพ|เอเชี่ยนคัพ|ช้างศึก|ทีมชาติไทย|คิงส์คัพ/i.test(text)) {
      leagueBadge = "🇹🇭 ช้างศึก / เอเชียนคัพ";
    } else if (/acl|เอเอฟซี|คาชิว่า|คาชิวะ|แอดิเลด/i.test(text)) {
      leagueBadge = "🌏 ACL เอเชีย";
    } else if (/บอลนักเรียน|นักเรียนไทย/i.test(text)) {
      leagueBadge = "🇹🇭 บอลนักเรียนโลก";
    } else {
      leagueBadge = "🇹🇭 ฟุตบอลไทย";
    }
    leagueBadgeClass = "bg-rose-900 text-rose-100 border border-rose-700/50";
  }
  // 10. Fallback Other Sports
  else {
    discipline = "other_sports";
    disciplineLabel = "กีฬาอื่นๆ";
    leagueBadge = "🏃 กีฬาอื่นๆ";
    leagueBadgeClass = "bg-slate-800 text-slate-200 border border-slate-700/50";
  }

  // Content type
  let contentType = "general";
  let contentTypeLabel = "ข่าวทั่วไป";
  let isResult = false;
  let scoreHighlight = "";

  if (/ผลบอล|ผลการแข่งขัน|คว้าชัย|บุกชนะ|เปิดบ้านชนะ|ชนะ|พ่าย|พ่ายยับ|แพ้|ถล่ม|เสมอกัน|เสมอ|คว้าแชมป์|คว้า 3 แต้ม|แฮตทริก|ตารางคะแนน|ล้มมือวาง/.test(title)) {
    contentType = "result";
    contentTypeLabel = "ผลการแข่งขัน";
    isResult = true;
    const scoreMatch = title.match(/(\d+[\s-–]\d+|\d+\s*คน|แฮตทริก|คว้า\s*3\s*แต้ม|คว้าแชมป์)/);
    if (scoreMatch) {
      scoreHighlight = scoreMatch[1];
    }
  } else if (/โปรแกรมบอล|เปิดโปรแกรม|โปรแกรมเตะ|ดูบอลสด|วิเคราะห์บอล|ตารางแข่ง|เปิดรับสมัคร|นัดแรกฟาดแข้ง|ฟาดแข้ง\s*\d+/.test(title)) {
    contentType = "schedule";
    contentTypeLabel = "โปรแกรมแข่ง";
  }

  return {
    discipline,
    disciplineLabel,
    leagueBadge,
    leagueBadgeClass,
    contentType,
    contentTypeLabel,
    isResult,
    scoreHighlight,
  };
}

export function checkIsSportsCluster(storyData, articles = []) {
  if (storyData && storyData.category === "sports") return true;
  if (!Array.isArray(articles) || !articles.length) return false;
  const validArticles = articles.filter(Boolean);
  if (!validArticles.length) return false;
  const sportsKw = /ucl|ชปล|พรีเมียร์ลีก|ไทยลีก|ฟุตบอล|กีฬา|วอลเลย์บอล|ลูกยาง|ผลบอล|แข่ง|แชมป์|แต้ม|สโมสร|นักเตะ|เอเอฟซี|แชมเปียนส์|แชมเปี้ยนส์|พาราเกมส์|เทนนิส|แบดมินตัน/;
  let sportsCount = 0;
  for (const a of validArticles) {
    if (a.category === "sports") {
      sportsCount++;
    } else if (a.url && (a.url.includes("/sport") || a.url.includes("/football") || a.url.includes("/ผลบอล"))) {
      sportsCount++;
    } else if (sportsKw.test(String(a.title || "").toLowerCase())) {
      sportsCount++;
    }
  }
  return (sportsCount / validArticles.length) >= 0.35;
}
