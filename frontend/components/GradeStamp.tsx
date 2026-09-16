import { GRADE_TITLE, type Grade } from "@/lib/types";

export default function GradeStamp({ grade }: { grade: Grade }) {
  return (
    <div className={`stamp ${grade}`} role="img" aria-label={`신뢰도 등급 ${grade}: ${GRADE_TITLE[grade]}`}>
      {grade}
      <span>신뢰도</span>
    </div>
  );
}
