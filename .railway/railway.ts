// Railway 배포 정의 (Infrastructure as Code). 적용: railway config plan → railway config apply
// 백엔드만 올린다. 프론트는 Netlify(netlify.toml)에서 서비스한다.
import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  // SQLite + 업로드 문서 + 검증 결과가 여기에 쌓인다 (Dockerfile의 DATA_DIR=/data).
  // Trial/Free 플랜 볼륨 상한이 0.5 GB라 500으로 시작. Hobby로 올리면 sizeMB를 키우면 된다.
  // 리전은 서비스와 같아야 한다(다르면 볼륨 마이그레이션 + 다운타임). 현재 서비스는 US West.
  const data = volume("backend-volume", { region: "sfo", sizeMB: 500 });

  const backend = service("backend", {
    // backend/Dockerfile을 자동 감지해서 빌드한다.
    source: github("leehun0720-hash/fact_checker", { branch: "main", rootDirectory: "backend" }),
    // backend/ 밖(프론트·문서)만 바뀐 커밋으로는 재배포하지 않는다. 재배포는 진행 중인 검증을 죽인다.
    build: { watchPatterns: ["/backend/**"] },
    healthcheck: "/api/health",
    healthcheckTimeout: 300, // Chromium 포함 이미지라 첫 기동이 느릴 수 있음
    env: {
      DATA_DIR: "/data",
      // 프론트 도메인. Netlify 도메인이 바뀌면 여기와 netlify.toml을 함께 고친다.
      CORS_ORIGINS: "https://zippy-unicorn-d4c02b.netlify.app,http://localhost:3000",
      // 첫 조직·관리자 계정을 화면에서 만들기 위해 켜 둔다. 만든 뒤 "0"으로 내리고 다시 apply.
      ALLOW_SELF_SIGNUP: "1",
      // "1"이면 Claude API를 부르지 않고 고정 샘플을 반환(데모). 키·스킬 ID가 있으면 "0".
      MOCK_VERIFIER: "0",
      CLAUDE_MODEL: "claude-opus-5",
      DFC_SKILL_VERSION: "latest",
      MAX_CONCURRENT_JOBS: "2",
      // 비밀값은 파일에 넣지 않는다. `railway variable set KEY=값`으로 넣고 여기서는 유지만 선언.
      ANTHROPIC_API_KEY: preserve(),
      DFC_SKILL_ID: preserve(),
      LAW_API_OC: preserve(),
    },
    volumeMounts: { "/data": data },
  });

  return project("fact-checker", { resources: [backend, data] });
});
