from bs4 import BeautifulSoup

def normalize_text(text):
    return (
        text
        .replace("\xa0", " ")
        .replace("\u00A0", " ")
        .strip()
    )

def extract_speaker_name(header_text) -> str | None:
    parts = header_text.strip().split(" ")

    parts = parts[1:]

    if len(parts) <= 1:
        return None

    name_parts = []

    i = len(parts) - 1

    while i >= 0:
        word = parts[i]

        if (
            word
            and word[0].isupper()
            and "minister" not in word.lower()
            and "esimees" not in word.lower()
        ):
            name_parts.insert(0, word)
            i -= 1
        else:
            break

    name = " ".join(name_parts).strip()

    return name if name else None


def parse_stenogram_speeches(soup: BeautifulSoup):
    speeches = []

    for block in soup.select("div.speech-area"):
        h4 = block.find("h4")

        if not h4:
            continue

        header_text = h4.get_text(" ", strip=True)
        header_text = normalize_text(header_text)
        speaker = extract_speaker_name(header_text)

        if not speaker:
            continue

        for inner in block.select("p p"):
            inner.unwrap()

        text_parts = []

        for p in block.find_all("p"):
            text = p.get_text(" ", strip=True)

            if text:
                text_parts.append(text)

        unique_parts = []

        for text in text_parts:
            if text not in unique_parts:
                unique_parts.append(text)

        full_text = "\n".join(unique_parts)
        full_text = normalize_text(full_text)

        if not full_text:
            continue

        speeches.append(
            {
                "speaker": speaker,
                "text": full_text,
            }
        )

    return speeches