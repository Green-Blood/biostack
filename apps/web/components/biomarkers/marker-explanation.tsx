"use client";
import { useI18n } from "@/lib/i18n/client";
import { AiMarkerGuide } from "./ai-marker-guide";

const explanations = {
  pdw: {
    ru: ["PDW — показатель общего анализа крови: он показывает, насколько тромбоциты различаются по размеру. Тромбоциты помогают останавливать кровотечение.", "При высоком PDW размеры тромбоцитов различаются сильнее; это может встречаться при изменении их образования или разрушения, но по одному PDW причину определить нельзя.", "При низком PDW тромбоциты более похожи по размеру. Сам по себе такой результат обычно не указывает на конкретную болезнь.", "PDW сам по себе не говорит, насколько хорошо сворачивается кровь и как вы будете себя чувствовать. Его оценивают вместе с количеством тромбоцитов (PLT), MPV, симптомами и остальным анализом."],
    en: ["PDW is part of a complete blood count. It measures how much platelets vary in size; platelets help stop bleeding.", "High PDW means platelet sizes vary more. It can occur when platelet production or destruction changes, but PDW alone cannot identify the cause.", "Low PDW means platelets are more similar in size. On its own it usually does not point to a specific disease.", "PDW alone cannot tell how well your blood clots or how you will feel. It is interpreted alongside platelet count (PLT), MPV, symptoms and the rest of the blood count."],
    source: "https://www.rcpa.edu.au/Manuals/RCPA-Manual/Pathology-Tests/P/Platelet-indices",
  },
  rdw: {
    ru: ["RDW — показатель общего анализа крови, отражающий различия эритроцитов по размеру. Эритроциты переносят кислород к тканям.", "Высокий RDW означает больший разброс размеров. Такое бывает, например, при некоторых видах анемии или дефиците железа, витамина B12 либо фолата; причина определяется по другим данным.", "Низкий RDW означает, что размеры эритроцитов близки друг к другу. Сам по себе он обычно не указывает на заболевание.", "RDW не объясняет симптомы самостоятельно. Врач рассматривает его вместе с гемоглобином, MCV и другими результатами; анемия может сопровождаться усталостью или одышкой."],
    en: ["RDW is part of a complete blood count and describes variation in red blood cell size. These cells carry oxygen to your tissues.", "High RDW means greater variation in size. It can occur with some types of anemia or iron, vitamin B12 or folate deficiency; other information is needed to find the cause.", "Low RDW means red blood cells are similar in size. On its own it usually does not indicate a disease.", "RDW alone does not explain symptoms. It is interpreted with hemoglobin, MCV and other results; anemia can cause tiredness or shortness of breath."],
    source: "https://medlineplus.gov/lab-tests/rdw-red-cell-distribution-width/",
  },
};

export function MarkerExplanation({ markerKey }: { markerKey: string }) {
  const { locale } = useI18n();
  const info = markerKey === "pdw" ? explanations.pdw : ["rdw_cv", "rdw_sd"].includes(markerKey) ? explanations.rdw : null;
  const ru = locale === "ru";
  return <section aria-labelledby="marker-explanation" className="space-y-3 rounded-xl border bg-card p-4 shadow-card sm:p-5">
    <h2 id="marker-explanation" className="text-xl">{ru ? "Что означает показатель" : "Understanding this marker"}</h2>
    {info ? <>
      <p>{info[locale][0]}</p>
      <p><strong>{ru ? "Если выше: " : "If high: "}</strong>{info[locale][1]}</p>
      <p><strong>{ru ? "Если ниже: " : "If low: "}</strong>{info[locale][2]}</p>
      <p>{info[locale][3]}</p>
      <a className="text-sm underline" href={info.source} target="_blank" rel="noreferrer">{ru ? "Источник" : "Source"}</a>
    </> : <AiMarkerGuide markerKey={markerKey} />}
    <p className="text-sm text-muted-foreground">{ru ? "Референсный диапазон зависит от лаборатории. Результат вне диапазона не обязательно означает болезнь, а результат в диапазоне не исключает её. Учитывайте симптомы и обсудите результат с врачом." : "Reference ranges vary by laboratory. A result outside the range does not necessarily mean disease, and a result within it does not rule disease out. Consider your symptoms and discuss the result with a clinician."} <a className="underline" href="https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/" target="_blank" rel="noreferrer">MedlinePlus</a></p>
  </section>;
}
