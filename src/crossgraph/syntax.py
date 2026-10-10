from .schemas import Chunk, Clause


class Syntax:
    def __init__(self, model_name: str, device: str = "cpu"):
        import spacy
        spacy.require_gpu() if device.startswith("cuda") else spacy.require_cpu()
        self.nlp = spacy.load(model_name)
        if not self.nlp.has_pipe("parser"):
            raise ValueError(f"spaCy model {model_name} has no dependency parser")

    def analyze(self, chunk: Chunk) -> list[Clause]:
        doc = self.nlp(chunk.text)
        clauses = []
        for sent in doc.sents:
            verbs = [t for t in sent if t.pos_ in {"VERB", "AUX"} and t.dep_ not in {"aux", "auxpass"}]
            for verb in verbs:
                children = list(verb.children)
                subj = next((t for t in children if t.dep_ in {"nsubj", "nsubjpass", "csubj"}), None)
                obj = next((t for t in children if t.dep_ in {"dobj", "obj", "attr", "acomp", "oprd"}), None)
                passive = bool(subj and subj.dep_ == "nsubjpass") or any(t.dep_ == "auxpass" for t in children)
                copular = bool(obj and obj.dep_ in {"attr", "acomp"}) or verb.lemma_ == "be"
                pattern = "SVC" if subj and copular else "SVO" if subj and obj else "SV" if subj else "OTHER"
                neg = any(t.dep_ == "neg" or t.lower_ in {"not", "never", "no"} for t in verb.subtree)
                modal = next((t.text for t in children if t.tag_ == "MD"), None)
                clauses.append(Clause(pattern=pattern, grammatical_subject=subj.text if subj else None, verb=verb.text, grammatical_object=obj.text if obj else None, voice="PASSIVE" if passive else "ACTIVE", polarity="NEGATIVE" if neg else "POSITIVE", modality=modal, start=sent.start_char, end=sent.end_char))
        return clauses
