# So sanh wet-mcp vs Context7 vs Tavily

## Phuong phap

30 thu vien **KHONG** co trong benchmark (1200 cases), da duoc kiem tra qua 3 cong cu:
- **wet-mcp**: Goi truc tiep `discover_library()` noi bo
- **Context7**: Goi MCP tool `resolve-library-id`
- **Tavily**: Goi MCP tool `tavily_search`

## Ket qua tong hop

| Metric | wet-mcp | Context7 | Tavily |
|--------|---------|----------|--------|
| Tim thay | 27/30 | 25/30 | 30/30 |
| Ti le | 90.0% | 83.3% | 100.0% |
| Muc dich | Official docs URL | Code snippets | General web search |

## Chi tiet theo thu vien

| # | Library | Lang | wet | C7 | Tavily | Ghi chu |
|---|---------|------|-----|-----|--------|---------|
| 1 | pydash | python | Y | **N** | Y | C7 tra ve Lightdash, Dash (sai) |
| 2 | python-multipart | python | Y | Y | Y | |
| 3 | pyjwt | python | Y | Y | Y | |
| 4 | passlib | python | Y | Y | Y | |
| 5 | textual | python | Y | Y | Y | |
| 6 | h3 | javascript | Y | Y | Y | C7 tra ve nhieu ket qua (unjs + uber h3) |
| 7 | nitro | javascript | Y | Y | Y | C7 tra ve nhieu ket qua (unjs + arbitrum + RN) |
| 8 | vinejs | javascript | **N** | Y | Y | wet: npm 404 |
| 9 | inertia | javascript | **N** | Y | Y | wet: npm tra ve package sai (constantology/inertia) |
| 10 | million | javascript | Y | Y | Y | |
| 11 | ratatui | rust | Y | Y | Y | |
| 12 | egui | rust | Y | Y | Y | |
| 13 | iced | rust | Y | Y | Y | |
| 14 | yew | rust | Y | Y | Y | |
| 15 | dioxus | rust | Y | Y | Y | |
| 16 | chi | go | Y | **N** | Y | C7 tra ve Python CHI (sai) |
| 17 | fx | go | Y | **N** | Y | C7 tra ve antonmedv/fx (JSON processor, sai) |
| 18 | consul | go | Y | Y | Y | |
| 19 | mediatr | csharp | Y | Y | Y | |
| 20 | fluentvalidation | csharp | Y | Y | Y | |
| 21 | dapper | csharp | Y | **N** | Y | C7 tra ve Dommel/Dapr (sai) |
| 22 | hibernate-validator | java | Y | **N** | Y | C7 tra ve Apache Commons Validator (sai) |
| 23 | resilience4j | java | Y | Y | Y | |
| 24 | pundit | ruby | Y | Y | Y | |
| 25 | dry-rb | ruby | **N** | Y | Y | wet: ko co tren rubygems (org umbrella) |
| 26 | doctrine | php | Y | Y | Y | |
| 27 | vitepress | javascript | Y | Y | Y | |
| 28 | quarto | python | Y | Y | Y | |
| 29 | hexo | javascript | Y | Y | Y | |
| 30 | caddy | go | Y | Y | Y | |

## Phan tich

### Diem manh cua tung tool:

1. **wet-mcp** (90%): Tim chinh xac URL docs CHINH THUC cua thu vien
   - Uu diem: Multi-registry (npm, PyPI, crates.io, pkg.go.dev, NuGet, Maven, Hex, Packagist, PubDev, RubyGems)
   - Nhuoc diem: Phu thuoc vao registry metadata, miss khi package ko co tren registry

2. **Context7** (83.3%): Tra ve code snippets tu thu vien da index
   - Uu diem: Pre-indexed, code snippets phong phu (len den 64000 snippets)
   - Nhuoc diem: Tim kiem theo ten, de bi nhieu boi ten chung (chi, fx, dapper)

3. **Tavily** (100%): Tim kiem web tong quat
   - Uu diem: Tim duoc moi thu
   - Nhuoc diem: ~40% la blog/tutorial, khong phan biet official vs third-party

### Bo sung lan nhau:
- wet miss 3 → Context7 tim duoc ca 3
- Context7 miss 5 → wet tim duoc ca 5
- Ket hop ca 2 = 30/30 (100%)

### Tavily chat luong tra ve:
- Official docs: ~30% (inertia.js)
- GitHub repos: ~30% (pydash, chi, vinejs, dry-rb)
- Blog/tutorials: ~40% (fx, dapper, hibernate-validator, egui)

## Ket luan

Cho use case **docs-mcp-server** (tim official docs URL de scrape):
- **wet-mcp** la lua chon tot nhat (90%, tra dung official URL)
- **Context7** bo sung tot cho code snippets
- **Tavily** dung nhu fallback cuoi cung

3 tool **KHONG** thay the nhau ma **BO SUNG** cho nhau.
