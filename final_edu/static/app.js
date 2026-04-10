(() => {
  "use strict";

  const state = {
    page1: {
      courses: [],
      selectedCourseId: "",
      selectedCourse: null,
      preview: null,
      previewFile: null,
      draftInstructorNames: [],
      blocks: [],
      blockData: {},
      courseDrafts: {},
      persistedCourseDrafts: {},
      menuOpenBlockId: "",
      instructorMenuOpenBlockId: "",
      restoringCourseId: "",
      restoreRequestId: 0,
      pendingPreparation: null,
      isPreparingAnalysis: false,
    },
    page2: {
      result: null,
      mode: "combined",
      instructorIndex: 0,
      instructorName: "",
      compareNames: [],
      charts: new Map(),
    },
    page3: {
      result: null,
    },
  };

  const CSS = {
    hidden: "is-hidden",
    open: "is-open",
    active: "is-active",
    disabled: "is-disabled",
    selected: "is-selected",
  };

  const SELECTORS = {
    page1CoursesData: "#page1-courses-data",
    page1CourseDraftsData: "#page1-course-drafts-data",
    courseModal: "#course-modal, [data-testid='course-modal']",
    courseListPanel: "#course-list-panel, [data-testid='course-list-panel']",
    courseModalForm: "#course-modal-form, [data-testid='course-modal-form']",
    coursePreviewState: "#course-preview-state, [data-testid='course-preview-state']",
    coursePreviewTable: "#course-preview-table, [data-testid='course-preview-table']",
    courseSaveButton: "#course-save-button, [data-testid='course-save-button']",
    courseFileTokens: "#course-file-tokens, [data-role='course-file-tokens']",
    courseInstructorInput: "#course-instructor-input, [data-testid='course-instructor-input']",
    courseInstructorTokens: "#course-instructor-tokens, [data-role='course-instructor-tokens']",
    courseInstructorNamesJson: "#course-instructor-names-json",
    analysisPrepareModal: "#analysis-prepare-modal, [data-testid='analysis-prepare-modal']",
    selectedCourseId: "#selected-course-id, [data-testid='selected-course-id']",
    selectedCourseName: "#selected-course-name, [data-testid='selected-course-name']",
    page1Workspace: "#page1-workspace, [data-testid='page1-workspace']",
    page1EmptyState: "[data-workspace-disabled]",
    instructorBlocks: "#instructor-blocks, [data-testid='instructor-blocks']",
    instructorBlockTemplate: "#instructor-block-template, [data-testid='instructor-block-template']",
    addInstructorBlock: "#add-instructor-block, [data-testid='add-instructor-block']",
    submitAnalysis: "#submit-analysis, [data-testid='submit-analysis']",
    analysisForm: "form[action='/analyze'], [data-testid='analysis-form']",
    courseForm: "#course-modal-form, [data-testid='course-modal-form']",
    openCourseModal: [
      "[data-open-course-modal]",
      "[data-testid='open-course-modal']",
      "[aria-controls='course-modal']",
      "#open-course-modal",
    ],
    openCourseList: [
      "[data-open-course-list]",
      "[data-testid='open-course-list']",
      "[aria-controls='course-list-panel']",
      "#open-course-list",
    ],
    closeDialogs: [
      "[data-close-dialog]",
      "[data-testid='close-dialog']",
      "[data-close='course-modal']",
      "[data-close='course-list-panel']",
    ],
    page2ResultData: "#page2-result-data, [data-testid='page2-result-data']",
    page2ModeButtons: [
      "[data-view-mode]",
      "[data-mode-toggle]",
      "[data-page2-mode]",
    ],
    page2InstructorButtons: [
      "[data-instructor-index]",
      "[data-instructor-name]",
      "[data-page2-instructor]",
    ],
    page2RoseChart: "#page2-rose-chart, [data-chart='rose']",
    page2WordCloud: "#page2-wordcloud-chart, [data-chart='wordcloud']",
    page2AverageBar: "#page2-average-bar-chart, [data-chart='average-bar']",
    page2InstructorBar: "#page2-instructor-bar-chart, [data-chart='instructor-bar']",
    page2LineChart: "#page2-line-chart, [data-chart='line']",
    page2SelectedInstructor: "#page2-selected-instructor, [data-testid='page2-selected-instructor'], [data-page2-selected-instructor]",
    page2InstructorNav: "[data-instructor-nav]",
    page2CompareAll: "[data-compare-all]",
    page2CompareInputs: "[data-compare-instructor]",
    page3ResultData: "#page3-result-data, [data-testid='page3-result-data']",
    page3InsightContainer: "#page3-insights, [data-page3-insights], [data-testid='page3-insights']",
    page3TrendStatus: "#page3-trend-status, [data-page3-trend-status], [data-testid='page3-trend-status']",
  };

  const CHART_COLORS = ["#2e303b", "#cd483f", "#888c67", "#e89b8d", "#92c393", "#edb6c3", "#b3d3c5", "#f2e7e7"];

  function init() {
    initPage1();
    initPage2();
    initPage3();
    window.FinalEduUI = { state };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  function initPage1() {
    const analysisForm = $(SELECTORS.analysisForm);
    const workspace = $(SELECTORS.page1Workspace);
    const courseForm = $(SELECTORS.courseForm);
    if (!analysisForm || !workspace || !courseForm) {
      return;
    }

    const coursesScript = $(SELECTORS.page1CoursesData);
    const courses = safeParseJSON(text(coursesScript), []);
    state.page1.courses = Array.isArray(courses) ? courses.map(normalizeCoursePayload) : [];
    const courseDraftsScript = $(SELECTORS.page1CourseDraftsData);
    state.page1.persistedCourseDrafts = normalizePersistedCourseDrafts(
      safeParseJSON(text(courseDraftsScript), {}),
    );

    const refs = {
      courseModal: $(SELECTORS.courseModal),
      courseListPanel: $(SELECTORS.courseListPanel),
      courseForm,
      analysisForm,
      workspace,
      prepareModal: $(SELECTORS.analysisPrepareModal),
      emptyState: $(SELECTORS.page1EmptyState),
      blocksRoot: $(SELECTORS.instructorBlocks),
      template: $(SELECTORS.instructorBlockTemplate),
      addBlockButton: $(SELECTORS.addInstructorBlock),
      submitButton: $(SELECTORS.submitAnalysis),
      saveButton: $(SELECTORS.courseSaveButton),
      previewState: $(SELECTORS.coursePreviewState),
      previewTable: $(SELECTORS.coursePreviewTable),
      selectedCourseId: ensureHiddenInput(analysisForm, "course_id"),
      selectedCourseName: ensureHiddenInput(analysisForm, "course_name"),
      manifestInput: ensureHiddenInput(analysisForm, "instructor_manifest"),
      courseFileInput: findFirst(courseForm, [
        "input[type='file'][name='curriculum_pdf']",
        "[data-testid='course-curriculum-file']",
      ]),
      courseNameInput: findFirst(courseForm, [
        "input[name='course_name']",
        "[data-testid='course-name']",
      ]),
      courseDropzone: findFirst(courseForm, [
        "[data-role='course-dropzone']",
        ".page1-file-dropzone",
      ]),
      courseFileTokens: $(SELECTORS.courseFileTokens),
      courseInstructorInput: $(SELECTORS.courseInstructorInput),
      courseInstructorTokens: $(SELECTORS.courseInstructorTokens),
      courseInstructorNamesJson: $(SELECTORS.courseInstructorNamesJson),
      prepareMode: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-mode']"]),
      prepareVideoCount: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-video-count']"]),
      prepareDuration: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-duration']"]),
      prepareChunks: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-chunks']"]),
      prepareProcessing: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-processing']"]),
      prepareCost: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-cost']"]),
      prepareCaptionProbe: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-caption-probe']"]),
      prepareCaptionSuccess: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-caption-success']"]),
      prepareCaptionTotal: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-caption-total']"]),
      preparePlaylistsBlock: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-playlists-block']"]),
      preparePlaylists: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-playlists']"]),
      prepareWarningsBlock: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-warnings-block']"]),
      prepareWarnings: findFirst($(SELECTORS.analysisPrepareModal), ["[data-role='prepare-warnings']"]),
      prepareConfirmButton: findFirst($(SELECTORS.analysisPrepareModal), ["[data-confirm-prepare]"]),
    };

    state.page1.selectedCourseId = valueOf(refs.selectedCourseId);
    state.page1.selectedCourse = state.page1.courses.find((item) => item.id === state.page1.selectedCourseId) || null;

    bindDialog(refs.courseModal, SELECTORS.openCourseModal, SELECTORS.closeDialogs);
    bindDialog(refs.courseListPanel, SELECTORS.openCourseList, SELECTORS.closeDialogs);
    bindPrepareModal(refs);

    if (refs.courseFileInput) {
      refs.courseFileInput.addEventListener("change", () => {
        handleCourseFileSelection(refs);
      });
    }

    if (refs.courseNameInput) {
      refs.courseNameInput.addEventListener("input", () => {
        updateCourseSaveButtonState(refs);
      });
    }

    if (refs.courseDropzone) {
      bindDropzone(refs.courseDropzone, {
        onFiles(files) {
          setCourseDraftFile(files[0] || null, refs);
        },
      });
    }

    if (refs.courseFileTokens) {
      refs.courseFileTokens.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const removeButton = target.closest("[data-remove-course-file]");
        if (!removeButton) {
          return;
        }
        event.preventDefault();
        clearCourseDraftFile(refs);
      });
    }

    if (refs.courseInstructorInput) {
      refs.courseInstructorInput.addEventListener("keydown", (event) => {
        if (event.key === "," || event.key === "Enter") {
          event.preventDefault();
          commitCourseInstructorDraft(refs.courseInstructorInput.value, refs);
        }
      });
      refs.courseInstructorInput.addEventListener("blur", () => {
        if (refs.courseInstructorInput.value.trim()) {
          commitCourseInstructorDraft(refs.courseInstructorInput.value, refs);
        }
      });
    }

    if (refs.courseInstructorTokens) {
      refs.courseInstructorTokens.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const removeButton = target.closest("[data-remove-course-instructor]");
        if (!removeButton) {
          return;
        }
        const index = Number(removeButton.getAttribute("data-remove-course-instructor"));
        if (Number.isNaN(index)) {
          return;
        }
        state.page1.draftInstructorNames.splice(index, 1);
        renderCourseInstructorTokens(refs);
        updateCourseSaveButtonState(refs);
      });
    }

    if (refs.previewTable) {
      refs.previewTable.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.closest("[data-preview-row]")) {
          return;
        }
        syncPreviewSectionsFromTable(refs.previewTable);
        updateCourseSaveButtonState(refs);
        renderCoursePreviewState(refs.previewState, state.page1.preview, refs.courseNameInput?.value || "");
      });
    }

    refs.courseForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!state.page1.preview) {
        await previewCourse(refs.courseForm, refs.courseFileInput, refs.courseNameInput, refs.previewState, refs.previewTable, refs.saveButton);
      }
      if (canSaveCourse(refs)) {
        await saveCourse(refs.courseForm, refs.courseFileInput, refs.courseNameInput, refs.previewState, refs.previewTable, refs.saveButton, refs.courseModal, refs);
      }
    });

    refs.analysisForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      syncAnalysisFormSubmission(refs);
      await prepareAnalysisSubmission(refs);
    });

    if (refs.addBlockButton) {
      refs.addBlockButton.addEventListener("click", (event) => {
        event.preventDefault();
        if (!canAddMoreBlocks()) {
          return;
        }
        addInstructorBlock(refs.blocksRoot, refs.template, refs.analysisForm, refs.manifestInput);
        syncPage1State(refs);
      });
    }

    if (refs.submitButton) {
      refs.submitButton.addEventListener("click", (event) => {
        event.preventDefault();
        refs.analysisForm.requestSubmit ? refs.analysisForm.requestSubmit(refs.submitButton) : refs.analysisForm.submit();
      });
    }

    if (refs.courseListPanel) {
      refs.courseListPanel.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const button = target.closest("[data-course-select]");
        if (!button) {
          return;
        }
        const courseId = button.getAttribute("data-course-select");
        const course = state.page1.courses.find((item) => item.id === courseId);
        if (!course) {
          return;
        }
        closeSurface(refs.courseListPanel);
        await selectCourse(course, refs);
      });
    }

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (!target.closest("[data-instructor-block]")) {
        closeAllBlockMenus();
      }
    });

    if (!state.page1.courses.length) {
      fetchCourses().then((items) => {
        if (!items.length) {
          return;
        }
        state.page1.courses = items.map(normalizeCoursePayload);
        renderCourseList(refs.courseListPanel);
        syncPage1State(refs);
      });
    } else {
      renderCourseList(refs.courseListPanel);
    }

    const existingBlocks = refs.blocksRoot ? qsa("[data-instructor-block]", refs.blocksRoot) : [];
    state.page1.blocks = [];
    state.page1.blockData = {};
    state.page1.instructorMenuOpenBlockId = "";
    if (!existingBlocks.length) {
      addInstructorBlock(refs.blocksRoot, refs.template, refs.analysisForm, refs.manifestInput);
    } else {
      existingBlocks.forEach((block, index) => {
        state.page1.blocks.push(block);
        bindInstructorBlock(block, index + 1);
      });
    }

    renderCourseFileTokens(refs);
    renderCourseInstructorTokens(refs);
    updateCourseSaveButtonState(refs);
    updateCourseListSelection(refs.courseListPanel);
    syncPage1State(refs);
    if (state.page1.selectedCourse) {
      selectCourse(state.page1.selectedCourse, refs).catch((error) => {
        console.error(error);
      });
    }
  }

  function initPage2() {
    const dataScript = $(SELECTORS.page2ResultData);
    const result = safeParseJSON(text(dataScript), null);
    if (!result || typeof result !== "object") {
      return;
    }
    state.page2.result = result;

    const containers = {
      rose: $(SELECTORS.page2RoseChart),
      wordcloud: $(SELECTORS.page2WordCloud),
      averageBar: $(SELECTORS.page2AverageBar),
      instructorBar: $(SELECTORS.page2InstructorBar),
      line: $(SELECTORS.page2LineChart),
      selectedInstructorTargets: qsa(SELECTORS.page2SelectedInstructor),
    };
    const modeButtons = qsa(joinSelectors(SELECTORS.page2ModeButtons));
    const instructorButtons = qsa(joinSelectors(SELECTORS.page2InstructorButtons));
    const compareAll = $(SELECTORS.page2CompareAll);
    const compareInputs = qsa(SELECTORS.page2CompareInputs);

    if (!result.instructors || !result.instructors.length) {
      return;
    }

    state.page2.instructorIndex = resolveInstructorIndex(
      result.selected_instructor || result.selectedInstructor || result.instructors[0].name,
      0,
    );
    state.page2.instructorName = result.instructors[state.page2.instructorIndex]?.name || result.selected_instructor || result.selectedInstructor || result.instructors[0].name;
    state.page2.compareNames = compareInputs.length
      ? compareInputs.filter((input) => input.checked).map((input) => input.value)
      : result.instructors.map((item) => item.name);

    modeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.getAttribute("data-view-mode") || button.getAttribute("data-mode-toggle") || button.getAttribute("data-page2-mode");
        if (!mode) {
          return;
        }
        state.page2.mode = normalizeMode(mode);
        syncModeButtons(modeButtons);
        updatePage2Charts(containers, { updateRoseWordcloud: true });
      });
    });
    syncModeButtons(modeButtons);

    instructorButtons.forEach((button, index) => {
      const instructorIndex = resolveInstructorIndex(button.getAttribute("data-instructor-index"), index);
      button.addEventListener("click", () => {
        selectPage2Instructor(
          button.getAttribute("data-instructor-index") ?? instructorIndex,
          containers,
          { updateRoseWordcloud: true, updateModeCharts: false, updateLine: false },
        );
      });
    });
    syncInstructorButtons(instructorButtons, state.page2.instructorIndex, state.page2.instructorName);

    if (compareAll) {
      compareAll.addEventListener("change", () => {
        compareInputs.forEach((input) => {
          input.checked = compareAll.checked;
        });
        syncComparisonSelection(compareInputs, compareAll);
        updatePage2Charts(containers, { updateRoseWordcloud: false, updateModeCharts: false, updateLine: true });
      });
    }

    compareInputs.forEach((input) => {
      input.addEventListener("change", () => {
        syncComparisonSelection(compareInputs, compareAll);
        updatePage2Charts(containers, { updateRoseWordcloud: false, updateModeCharts: false, updateLine: true });
      });
    });

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const nav = target.closest(SELECTORS.page2InstructorNav);
      if (!nav || !state.page2.result) {
        return;
      }
      const direction = nav.getAttribute("data-instructor-nav");
      if (direction !== "prev" && direction !== "next") {
        return;
      }
      event.preventDefault();
      selectPage2Instructor(
        direction === "prev" ? state.page2.instructorIndex - 1 : state.page2.instructorIndex + 1,
        containers,
        { updateRoseWordcloud: true, updateModeCharts: false, updateLine: false },
      );
    });

    syncComparisonSelection(compareInputs, compareAll);
    updatePage2Charts(containers);
    window.addEventListener("resize", debounce(() => resizeCharts(), 100));
  }

  function initPage3() {
    const dataScript = $(SELECTORS.page3ResultData);
    const result = safeParseJSON(text(dataScript), null);
    if (!result || typeof result !== "object") {
      return;
    }
    state.page3.result = result;
    const root = $(SELECTORS.page3InsightContainer);
    if (root && !root.children.length) {
      renderInsights(root, result);
    }
    const trendStatus = $(SELECTORS.page3TrendStatus);
    if (trendStatus) {
      const trendMeta = trendStatusMeta(result.external_trends_status);
      trendStatus.textContent = trendMeta.message;
      trendStatus.classList.remove("is-planned", "is-success", "is-failed", "is-unknown");
      trendStatus.classList.add(trendMeta.className);
    }
  }

  function previewCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton) {
    if (!courseForm || !courseFileInput || !courseFileInput.files || !courseFileInput.files.length) {
      setStatus(previewState, "PDF 파일을 선택해 주세요.");
      return Promise.resolve(null);
    }
    const file = courseFileInput.files[0];
    if (!file) {
      setStatus(previewState, "PDF 파일을 선택해 주세요.");
      return Promise.resolve(null);
    }

    const fd = new FormData();
    fd.append("curriculum_pdf", file, file.name);
    state.page1.previewFile = file;
    setBusy(saveButton, true);
    setStatus(previewState, "커리큘럼 PDF를 분석하는 중입니다.");

    return fetchJson("/courses/preview", {
      method: "POST",
      body: fd,
    })
      .then((payload) => {
        state.page1.preview = normalizePreview(payload);
        renderCoursePreview(previewTable, previewState, state.page1.preview, courseNameInput?.value || "");
        setBusy(saveButton, false);
        updateCourseSaveButtonState({
          courseNameInput,
          saveButton,
          courseInstructorNamesJson: $(SELECTORS.courseInstructorNamesJson),
        });
        return state.page1.preview;
      })
      .catch((error) => {
        setStatus(previewState, `미리보기에 실패했습니다. ${error.message}`);
        setBusy(saveButton, false);
        setButtonDisabled(saveButton, true);
        return null;
      });
  }

  function saveCourse(courseForm, courseFileInput, courseNameInput, previewState, previewTable, saveButton, courseModal, refs) {
    if (!state.page1.preview || !courseFileInput?.files?.length) {
      setStatus(previewState, "먼저 PDF를 미리보기로 분석해 주세요.");
      return Promise.resolve(null);
    }

    const fd = new FormData();
    fd.append("course_name", courseNameInput?.value?.trim() || "이름 없는 과정");
    fd.append("raw_curriculum_text", state.page1.preview.raw_curriculum_text || "");
    fd.append("sections_json", JSON.stringify(readPreviewSections(previewTable)));
    fd.append("instructor_names_json", JSON.stringify(state.page1.draftInstructorNames));
    fd.append("curriculum_pdf", courseFileInput.files[0], courseFileInput.files[0].name);
    setBusy(saveButton, true);

    return fetchJson("/courses", {
      method: "POST",
      body: fd,
    })
      .then((payload) => {
        state.page1.courses = Array.isArray(payload.courses) ? payload.courses.map(normalizeCoursePayload) : state.page1.courses;
        if (payload.course) {
          return selectCourse(normalizeCoursePayload(payload.course), refs).then(() => payload);
        }
        renderCourseList(refs.courseListPanel);
        setStatus(previewState, "과정이 저장되었습니다.");
        if (courseModal) {
          closeSurface(courseModal);
        }
        resetCourseDraft(refs);
        setBusy(saveButton, false);
        updateCourseSaveButtonState(refs);
        return payload;
      })
      .then((payload) => {
        if (!payload) {
          return null;
        }
        renderCourseList(refs.courseListPanel);
        setStatus(previewState, "과정이 저장되었습니다.");
        if (courseModal) {
          closeSurface(courseModal);
        }
        resetCourseDraft(refs);
        setBusy(saveButton, false);
        updateCourseSaveButtonState(refs);
        return payload;
      })
      .catch((error) => {
        setStatus(previewState, `저장에 실패했습니다. ${error.message}`);
        setBusy(saveButton, false);
        updateCourseSaveButtonState(refs);
        return null;
      });
  }

  function renderCoursePreview(previewTable, previewState, preview, courseName) {
    if (!previewTable) {
      return;
    }
    previewTable.innerHTML = "";
    previewTable.dataset.sectionCount = String(preview.sections.length);
    renderCoursePreviewState(previewState, preview, courseName);
    renderCoursePreviewTable(previewTable, preview);

    const sectionsInput = $("#course-sections-json");
    const rawTextInput = $("#course-raw-curriculum-text");
    if (sectionsInput) {
      sectionsInput.value = JSON.stringify(preview.sections);
    }
    if (rawTextInput) {
      rawTextInput.value = preview.raw_curriculum_text || "";
    }
  }

  function readPreviewSections(previewTable) {
    syncPreviewSectionsFromTable(previewTable);
    return Array.isArray(state.page1.preview?.sections) ? state.page1.preview.sections : [];
  }

  function renderCourseList(courseListPanel) {
    if (!courseListPanel) {
      return;
    }
    const target = ensureRenderedContainer(courseListPanel, "course-list-items", "div");
    target.innerHTML = "";
    if (!state.page1.courses.length) {
      const empty = document.createElement("p");
      empty.className = "course-list-empty";
      empty.textContent = "추가된 과정이 없습니다.";
      target.appendChild(empty);
      return;
    }

    state.page1.courses.forEach((course) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "course-list-item";
      card.dataset.courseSelect = course.id;
      card.dataset.courseItem = "true";
      if (course.id === state.page1.selectedCourseId) {
        card.classList.add(CSS.selected);
      }
      card.innerHTML = `
        <div class="course-list-item-head">
          <strong>${escapeHtml(course.name)}</strong>
          <span class="course-state-chip is-sage">선택 가능</span>
        </div>
        <span>등록 강사 ${Array.isArray(course.instructor_names) ? course.instructor_names.length : 0}명</span>
        <small>대주제 ${course.sections.length}개</small>
      `;
      target.appendChild(card);
    });
  }

  function updateCourseListSelection(courseListPanel) {
    qsa("[data-course-card]").forEach((button) => {
      const active = (button.getAttribute("data-course-select") || button.getAttribute("data-course-id")) === state.page1.selectedCourseId;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
    });
    if (!courseListPanel) {
      return;
    }
    qsa("[data-course-item]", courseListPanel).forEach((button) => {
      const active = button.getAttribute("data-course-select") === state.page1.selectedCourseId;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
    });
  }

  function formatCourseWeightTotal(sections) {
    const total = (Array.isArray(sections) ? sections : []).reduce((sum, section) => sum + Number(section?.target_weight || 0), 0);
    return total.toFixed(1);
  }

  async function selectCourse(course, refs) {
    const normalizedCourse = normalizeCoursePayload(course);
    const previousCourseId = state.page1.selectedCourseId;
    if (previousCourseId && previousCourseId !== normalizedCourse.id) {
      cacheCurrentCourseDraft(previousCourseId);
    }
    state.page1.selectedCourse = normalizedCourse;
    state.page1.selectedCourseId = normalizedCourse.id;
    state.page1.restoringCourseId = normalizedCourse.id;
    const restoreRequestId = ++state.page1.restoreRequestId;
    const { selectedCourseId, selectedCourseName, courseListPanel } = refs;

    setFieldValue(selectedCourseId, normalizedCourse.id);
    setFieldValue(selectedCourseName, normalizedCourse.name);
    state.page1.preview = null;
    state.page1.previewFile = null;

    if (previousCourseId !== normalizedCourse.id) {
      let restored = false;
      try {
        restored = await restoreCourseDraftForSelection(normalizedCourse.id, refs, restoreRequestId);
      } catch (error) {
        console.error(error);
      }
      if (!restored && restoreRequestId === state.page1.restoreRequestId) {
        resetPage1Blocks(refs.blocksRoot, refs.template, refs.analysisForm, refs.manifestInput);
      }
    }
    if (restoreRequestId === state.page1.restoreRequestId) {
      state.page1.restoringCourseId = "";
    }
    renderCourseList(courseListPanel);
    updateCourseListSelection(courseListPanel);
    syncPage1State(refs);
  }

  function normalizePersistedCourseDrafts(payload) {
    if (!payload || typeof payload !== "object") {
      return {};
    }
    return Object.entries(payload).reduce((acc, [courseId, draft]) => {
      const normalized = normalizeCourseDraft(draft);
      if (normalized.blocks.length) {
        acc[courseId] = normalized;
      }
      return acc;
    }, {});
  }

  function normalizeCourseDraft(draft) {
    const blocks = Array.isArray(draft?.blocks) ? draft.blocks.map(normalizeCourseDraftBlock).filter(Boolean) : [];
    return {
      courseId: String(draft?.course_id || draft?.courseId || ""),
      jobId: String(draft?.job_id || draft?.jobId || ""),
      updatedAt: String(draft?.updated_at || draft?.updatedAt || ""),
      updatedAtLabel: String(draft?.updated_at_label || draft?.updatedAtLabel || ""),
      blocks,
    };
  }

  function normalizeCourseDraftBlock(block) {
    if (!block || typeof block !== "object") {
      return null;
    }
    const files = Array.isArray(block.files)
      ? block.files
        .map((file) => {
          if (file instanceof File) {
            return file;
          }
          if (!file || typeof file !== "object") {
            return null;
          }
          return {
            originalName: String(file.original_name || file.originalName || file.name || ""),
            downloadUrl: String(file.download_url || file.downloadUrl || ""),
          };
        })
        .filter((file) => file && (file instanceof File || file.originalName))
      : [];
    const youtubeUrls = Array.isArray(block.youtube_urls || block.youtubeUrls)
      ? (block.youtube_urls || block.youtubeUrls).map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    const vocFiles = Array.isArray(block.voc_files || block.vocFiles)
      ? (block.voc_files || block.vocFiles)
        .map((file) => {
          if (file instanceof File) {
            return file;
          }
          if (!file || typeof file !== "object") {
            return null;
          }
          return {
            originalName: String(file.original_name || file.originalName || file.name || ""),
            downloadUrl: String(file.download_url || file.downloadUrl || ""),
          };
        })
        .filter((file) => file && (file instanceof File || file.originalName))
      : [];
    const instructorName = String(block.instructor_name || block.instructorName || "").trim();
    const mode = block.mode === "youtube" ? "youtube" : (block.mode === "voc" ? "voc" : "files");
    if (!instructorName && !files.length && !youtubeUrls.length && !vocFiles.length) {
      return null;
    }
    return {
      mode: files.length ? mode : (youtubeUrls.length ? "youtube" : (vocFiles.length ? "voc" : mode)),
      instructorName,
      files,
      vocFiles,
      youtubeUrls,
    };
  }

  function cacheCurrentCourseDraft(courseId) {
    const normalizedCourseId = String(courseId || "").trim();
    if (!normalizedCourseId) {
      return;
    }
    state.page1.courseDrafts[normalizedCourseId] = snapshotCurrentCourseDraft();
  }

  function snapshotCurrentCourseDraft() {
    const blocks = state.page1.blocks
      .map((block) => snapshotBlockState(getBlockState(block), block))
      .filter((block) => block.instructorName || block.files.length || block.vocFiles.length || block.youtubeUrls.length);
    return {
      blocks: blocks.length ? blocks : [createEmptyDraftBlock()],
    };
  }

  function snapshotBlockState(blockState, block = null) {
    return {
      mode: blockState.mode === "youtube" ? "youtube" : (blockState.mode === "voc" ? "voc" : "files"),
      instructorName: resolveBlockInstructorName(block, blockState),
      files: Array.isArray(blockState.files) ? blockState.files.slice() : [],
      vocFiles: Array.isArray(blockState.vocFiles) ? blockState.vocFiles.slice() : [],
      youtubeUrls: Array.isArray(blockState.youtubeUrls) ? blockState.youtubeUrls.slice() : [],
    };
  }

  function createEmptyDraftBlock() {
    return {
      mode: "files",
      instructorName: "",
      files: [],
      vocFiles: [],
      youtubeUrls: [],
    };
  }

  async function restoreCourseDraftForSelection(courseId, refs, restoreRequestId) {
    const normalizedCourseId = String(courseId || "").trim();
    const localDraft = state.page1.courseDrafts[normalizedCourseId];
    if (localDraft?.blocks?.length) {
      applyCourseDraft(refs, localDraft);
      return true;
    }

    const persistedDraft = state.page1.persistedCourseDrafts[normalizedCourseId];
    if (!persistedDraft?.blocks?.length) {
      return false;
    }

    const resolvedDraft = await resolvePersistedCourseDraft(persistedDraft, normalizedCourseId, restoreRequestId);
    if (!resolvedDraft || restoreRequestId !== state.page1.restoreRequestId || state.page1.selectedCourseId !== normalizedCourseId) {
      return false;
    }
    state.page1.courseDrafts[normalizedCourseId] = resolvedDraft;
    applyCourseDraft(refs, resolvedDraft);
    return true;
  }

  async function resolvePersistedCourseDraft(draft, courseId, restoreRequestId) {
    const usedFallbackNames = new Set();
    const resolvedBlocks = [];
    for (const [index, block] of (Array.isArray(draft.blocks) ? draft.blocks : []).entries()) {
      const restoredFiles = await Promise.all(
        (Array.isArray(block.files) ? block.files : []).map((file) => restoreDraftFile(file)),
      );
      const restoredVocFiles = await Promise.all(
        (Array.isArray(block.vocFiles) ? block.vocFiles : []).map((file) => restoreDraftFile(file)),
      );
      if (restoreRequestId !== state.page1.restoreRequestId || state.page1.selectedCourseId !== courseId) {
        return null;
      }
      const instructorName = resolveRestoredInstructorName(block.instructorName, courseId, index, usedFallbackNames);
      if (instructorName && currentCourseInstructorNamesForCourse(courseId).includes(instructorName)) {
        usedFallbackNames.add(instructorName);
      }
      resolvedBlocks.push({
        mode: block.mode === "youtube"
          ? "youtube"
          : (block.mode === "voc" ? "voc" : (restoredFiles.length ? "files" : (restoredVocFiles.length ? "voc" : "youtube"))),
        instructorName,
        files: restoredFiles.filter((file) => file instanceof File),
        vocFiles: restoredVocFiles.filter((file) => file instanceof File),
        youtubeUrls: Array.isArray(block.youtubeUrls) ? block.youtubeUrls.slice() : [],
      });
    }

    const meaningfulBlocks = resolvedBlocks.filter(
      (block) => block && (block.instructorName || block.files.length || block.vocFiles.length || block.youtubeUrls.length),
    );
    if (!meaningfulBlocks.length) {
      return null;
    }
    return { blocks: meaningfulBlocks };
  }

  async function restoreDraftFile(file) {
    if (file instanceof File) {
      return file;
    }
    const originalName = String(file?.originalName || file?.original_name || file?.name || "").trim();
    const downloadUrl = String(file?.downloadUrl || file?.download_url || "").trim();
    if (!originalName || !downloadUrl) {
      return null;
    }
    const response = await fetch(downloadUrl, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(`${originalName}: 저장된 자료를 다시 불러오지 못했습니다.`);
    }
    const blob = await response.blob();
    return new File([blob], originalName, {
      type: blob.type || "application/octet-stream",
      lastModified: Date.now(),
    });
  }

  function applyCourseDraft(refs, draft) {
    const snapshots = Array.isArray(draft?.blocks) && draft.blocks.length
      ? draft.blocks.map((block) => snapshotBlockState(block))
      : [createEmptyDraftBlock()];
    rebuildPage1Blocks(refs.blocksRoot, refs.template, refs.analysisForm, refs.manifestInput, snapshots);
  }

  function syncPage1State(refs) {
    const { workspace, emptyState, selectedCourseId, selectedCourseName, submitButton, manifestInput, addBlockButton } = refs;
    const selectedId = state.page1.selectedCourseId || valueOf(selectedCourseId);
    const selectedCourse = state.page1.courses.find((item) => item.id === selectedId) || state.page1.selectedCourse;
    state.page1.selectedCourse = selectedCourse || null;
    state.page1.selectedCourseId = selectedCourse?.id || "";

    setFieldValue(selectedCourseId, selectedCourse?.id || "");
    setFieldValue(selectedCourseName, selectedCourse?.name || "");

    if (workspace) {
      workspace.dataset.state = selectedCourse ? "active" : "disabled";
      workspace.classList.toggle(CSS.disabled, !selectedCourse);
    }
    if (emptyState) {
      emptyState.classList.toggle(CSS.hidden, Boolean(selectedCourse));
    }

    if (manifestInput) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }

    state.page1.blocks.forEach((block) => {
      renderBlock(block);
      setBlockDisabled(block, !selectedCourse);
    });

    if (addBlockButton) {
      setButtonDisabled(addBlockButton, !canAddMoreBlocks());
    }
    if (submitButton) {
      setButtonDisabled(submitButton, !canSubmitAnalysis());
    }

    updateCourseSaveButtonState(refs);
  }

  function syncAnalysisFormSubmission(refs) {
    if (!refs?.analysisForm) {
      return;
    }
    state.page1.blocks.forEach((block) => {
      const blockState = getBlockState(block);
      const instructorName = resolveBlockInstructorName(block, blockState);
      blockState.instructorName = instructorName;
      const instructorInput = findOne(block, ["[data-role='instructor-name']"]);
      const youtubeHidden = findOne(block, ["[data-role='instructor-youtube']"]);
      setFieldValue(instructorInput, instructorName);
      setFieldValue(youtubeHidden, blockState.youtubeUrls.join("\n"));
      syncBlockFileInput(block);
      renderBlock(block);
    });
    if (refs.manifestInput) {
      refs.manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }
  }

  async function prepareAnalysisSubmission(refs) {
    if (!refs?.analysisForm || state.page1.isPreparingAnalysis) {
      return;
    }
    if (!canSubmitAnalysis()) {
      setStatus(refs.previewState, "과정을 선택하고 강사 1명 이상에게 자료를 연결해 주세요.");
      return;
    }

    state.page1.isPreparingAnalysis = true;
    setButtonDisabled(refs.submitButton, true);
    try {
      const payload = await fetchJson("/analyze/prepare", {
        method: "POST",
        body: new FormData(refs.analysisForm),
      });
      state.page1.pendingPreparation = payload;
      if (payload.requires_confirmation) {
        renderPrepareSummary(refs, payload);
        openSurface(refs.prepareModal);
        return;
      }
      await confirmPreparedAnalysis(refs, payload.request_id);
    } catch (error) {
      setStatus(refs.previewState, `분석 준비에 실패했습니다. ${error.message}`);
    } finally {
      state.page1.isPreparingAnalysis = false;
      syncPage1State(refs);
    }
  }

  function bindPrepareModal(refs) {
    if (!refs?.prepareModal) {
      return;
    }
    qsa("[data-close-prepare]", refs.prepareModal).forEach((button) => {
      button.addEventListener("click", () => closePrepareModal(refs));
    });
    if (refs.prepareConfirmButton) {
      refs.prepareConfirmButton.addEventListener("click", async () => {
        const requestId = String(state.page1.pendingPreparation?.request_id || "").trim();
        if (!requestId) {
          return;
        }
        await confirmPreparedAnalysis(refs, requestId);
      });
    }
    refs.prepareModal.addEventListener("click", (event) => {
      if (event.target === refs.prepareModal) {
        closePrepareModal(refs);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isOpen(refs.prepareModal)) {
        closePrepareModal(refs);
      }
    });
  }

  function closePrepareModal(refs) {
    state.page1.pendingPreparation = null;
    if (refs?.prepareModal) {
      closeSurface(refs.prepareModal);
    }
  }

  async function confirmPreparedAnalysis(refs, requestId) {
    if (!requestId) {
      return;
    }
    setBusy(refs.prepareConfirmButton, true, "시작 중");
    try {
      const payload = await fetchJson(`/analyze/prepare/${encodeURIComponent(requestId)}/confirm`, {
        method: "POST",
      });
      closePrepareModal(refs);
      if (payload.redirect_url) {
        window.location.href = payload.redirect_url;
      }
    } catch (error) {
      setStatus(refs.previewState, `분석 시작에 실패했습니다. ${error.message}`);
    } finally {
      setBusy(refs.prepareConfirmButton, false);
    }
  }

  function renderPrepareSummary(refs, payload) {
    setFieldValue(refs.prepareMode, formatPrepareMode(payload.recommended_analysis_mode));
    setFieldValue(refs.prepareVideoCount, `${Number(payload.expanded_video_count || 0)}개`);
    setFieldValue(refs.prepareDuration, formatDurationSeconds(payload.total_video_duration_seconds || 0));
    setFieldValue(refs.prepareChunks, `${Number(payload.estimated_chunk_count || 0)}개`);
    setFieldValue(refs.prepareProcessing, formatDurationSeconds(payload.estimated_processing_seconds || 0));
    setFieldValue(refs.prepareCost, formatUsd(payload.estimated_cost_usd || 0));
    setFieldValue(refs.prepareCaptionSuccess, String(Number(payload.caption_probe_success_count || 0)));
    setFieldValue(refs.prepareCaptionTotal, String(Number(payload.caption_probe_sample_count || 0)));

    if (refs.preparePlaylists) {
      refs.preparePlaylists.innerHTML = "";
      const playlistSummaries = Array.isArray(payload.playlist_summaries) ? payload.playlist_summaries : [];
      playlistSummaries.forEach((summary) => {
        const item = document.createElement("article");
        item.className = "analysis-prepare-item";
        item.innerHTML = `
          <strong>${escapeHtml(summary.title || "YouTube Playlist")}</strong>
          <span>${escapeHtml(summary.instructor_name || "강사")} · ${Number(summary.expanded_video_count || summary.video_count || 0)}개 영상 · ${escapeHtml(formatDurationSeconds(summary.total_duration_seconds || 0))}</span>
        `;
        refs.preparePlaylists.appendChild(item);
      });
      if (refs.preparePlaylistsBlock) {
        refs.preparePlaylistsBlock.hidden = !playlistSummaries.length;
      }
    }

    if (refs.prepareWarnings) {
      refs.prepareWarnings.innerHTML = "";
      const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
      warnings.forEach((warning) => {
        const item = document.createElement("li");
        item.textContent = warning;
        refs.prepareWarnings.appendChild(item);
      });
      if (refs.prepareWarningsBlock) {
        refs.prepareWarningsBlock.hidden = !warnings.length;
      }
    }
  }

  function enableWorkspaceInputs() {
    // Page 1 now uses per-lane disabled state instead of disabling the full workspace tree.
  }

  function addInstructorBlock(blocksRoot, template, analysisForm, manifestInput) {
    if (!blocksRoot) {
      return null;
    }
    const index = state.page1.blocks.length + 1;
    const blockId = uniqueId("instructor");
    const block = createInstructorBlock(blockId, index, template);
    blocksRoot.appendChild(block);
    state.page1.blocks.push(block);
    bindInstructorBlock(block, index);
    syncPage1State(page1Refs());
    if (analysisForm) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }
    return block;
  }

  function createInstructorBlock(blockId, index, template) {
    if (template && template.content) {
      const fragment = template.content.cloneNode(true);
      const node = fragment.firstElementChild || fragment.firstElementChild;
      const block = node || fragment;
      if (block instanceof HTMLElement) {
        block.dataset.instructorBlock = "true";
        block.dataset.blockId = blockId;
        decorateInstructorBlock(block, blockId, index);
        return block;
      }
    }

    const block = document.createElement("article");
    block.className = "composer-lane";
    block.dataset.instructorBlock = "true";
    block.dataset.blockId = blockId;
    block.innerHTML = `
      <div class="composer-lane__start">
        <button type="button" class="lane-trigger" data-action="toggle-mode-menu" aria-label="업로드 방식 선택">+</button>
        <div class="lane-mode-menu" data-role="mode-menu" hidden>
          <button type="button" class="lane-mode-menu__item" data-action="switch-mode" data-mode="files">강의자료</button>
          <button type="button" class="lane-mode-menu__item" data-action="switch-mode" data-mode="youtube">강의영상</button>
          <button type="button" class="lane-mode-menu__item" data-action="switch-mode" data-mode="voc">강의평가</button>
        </div>
      </div>
      <div class="composer-lane__main">
        <div class="lane-surface lane-surface-files" data-role="files-surface">
          <input class="sr-only" type="file" multiple accept=".pdf,.pptx,.txt,.md" data-role="instructor-files" name="instructor_files__${blockId}">
          <button type="button" class="lane-surface__tap" data-action="open-file-picker">강의 자료를 드래그하거나 클릭해 업로드</button>
        </div>
        <div class="lane-surface lane-surface-youtube" data-role="youtube-surface" hidden>
          <div class="lane-token-shell">
            <input type="text" class="lane-token-input" data-role="youtube-draft" placeholder="유튜브 링크를 입력하고 콤마를 누르세요">
          </div>
          <input type="hidden" data-role="instructor-youtube" name="instructor_youtube_urls__${blockId}" value="">
        </div>
        <div class="lane-surface lane-surface-voc" data-role="voc-surface" hidden>
          <input class="sr-only" type="file" multiple accept=".pdf,.csv,.txt" data-role="instructor-voc" name="instructor_voc__${blockId}">
          <button type="button" class="lane-surface__tap" data-action="open-file-picker">강의평가서(VOC)를 드래그하거나 클릭해 업로드</button>
        </div>
        <div class="lane-asset-rail" data-role="asset-rail" hidden>
          <div class="lane-asset-strip" data-role="asset-list"></div>
        </div>
      </div>
      <div class="composer-lane__end">
        <input type="hidden" data-role="instructor-name" name="instructor_name__${blockId}" value="">
        <button type="button" class="instructor-picker-button" data-action="toggle-instructor-menu" aria-label="강사 선택" aria-haspopup="menu" aria-expanded="false" title="강사 선택">
          <svg viewBox="0 0 24 24" role="img" focusable="false">
            <path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-3.68 0-6.67 1.79-6.67 4v1h13.34v-1c0-2.21-2.99-4-6.67-4Z"></path>
          </svg>
        </button>
        <div class="instructor-picker-menu" data-role="instructor-menu" hidden></div>
      </div>
      <div class="composer-lane__meta" data-role="block-status">자료 없음</div>
    `;
    decorateInstructorBlock(block, blockId, index);
    return block;
  }

  function decorateInstructorBlock(block, blockId, index) {
    block.dataset.instructorBlock = "true";
    block.dataset.blockId = blockId;
    block.dataset.blockIndex = String(index);

    const instructorInput = findOne(block, ["[data-role='instructor-name']", "input[type='hidden']"]);
    const fileInput = findOne(block, ["[data-role='instructor-files']", "input[type='file']"]);
    const youtubeInput = findOne(block, ["[data-role='instructor-youtube']", "input[type='hidden']"]);
    const vocInput = findOne(block, ["[data-role='instructor-voc']", "input[type='file']"]);
    if (instructorInput) {
      instructorInput.name = `instructor_name__${blockId}`;
      instructorInput.id = `instructor-select-${blockId}`;
    }
    if (fileInput) {
      fileInput.name = `instructor_files__${blockId}`;
    }
    if (youtubeInput) {
      youtubeInput.name = `instructor_youtube_urls__${blockId}`;
    }
    if (vocInput) {
      vocInput.name = `instructor_voc__${blockId}`;
    }
    state.page1.blockData[blockId] = state.page1.blockData[blockId] || {
      mode: "files",
      instructorName: "",
      files: [],
      vocFiles: [],
      youtubeUrls: [],
    };
    renderBlock(block);
  }

  function bindInstructorBlock(block, index) {
    const blockId = block.dataset.blockId || uniqueId("instructor");
    decorateInstructorBlock(block, blockId, index);

    bindDropzone(block, {
      canAccept() {
        return canAcceptBlockFileDrop(block);
      },
      onFiles(files) {
        const blockState = getBlockState(block);
        const type = blockState.mode === "voc" ? "voc" : "files";
        addBlockFiles(block, files, type);
      },
    });

    block.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const action = target.closest("[data-action]");
      if (action) {
        const actionName = action.getAttribute("data-action");
        if (actionName === "toggle-mode-menu") {
          event.preventDefault();
          toggleModeMenu(block);
          return;
        }
        if (actionName === "toggle-instructor-menu") {
          event.preventDefault();
          toggleInstructorMenu(block);
          return;
        }
        if (actionName === "switch-mode") {
          event.preventDefault();
          switchBlockMode(block, action.getAttribute("data-mode") || "files");
          return;
        }
        if (actionName === "open-file-picker") {
          event.preventDefault();
          const blockState = getBlockState(block);
          const role = blockState.mode === "voc" ? "instructor-voc" : "instructor-files";
          const fileInput = findOne(block, [`[data-role='${role}']`]);
          if (fileInput) {
            fileInput.click();
          }
          return;
        }
        if (actionName === "select-instructor") {
          event.preventDefault();
          const blockState = getBlockState(block);
          blockState.instructorName = (action.getAttribute("data-instructor-value") || "").trim();
          state.page1.instructorMenuOpenBlockId = "";
          renderBlock(block);
          syncPage1State(page1Refs());
          return;
        }
      }

      const removeFileButton = target.closest("[data-remove-file-index]");
      if (removeFileButton) {
        event.preventDefault();
        removeBlockFile(block, Number(removeFileButton.getAttribute("data-remove-file-index")), "files");
        return;
      }

      const removeVocButton = target.closest("[data-remove-voc-index]");
      if (removeVocButton) {
        event.preventDefault();
        removeBlockFile(block, Number(removeVocButton.getAttribute("data-remove-voc-index")), "voc");
        return;
      }

      const removeUrlButton = target.closest("[data-remove-youtube-index]");
      if (removeUrlButton) {
        event.preventDefault();
        removeBlockYoutubeUrl(block, Number(removeUrlButton.getAttribute("data-remove-youtube-index")));
      }
    });

    block.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.matches("[data-role='instructor-files']")) {
        addBlockFiles(block, Array.from(target.files || []), "files");
        return;
      }
      if (target.matches("[data-role='instructor-voc']")) {
        addBlockFiles(block, Array.from(target.files || []), "voc");
        return;
      }
    });

    block.addEventListener("keydown", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (!target.matches("[data-role='youtube-draft']")) {
        return;
      }
      if (event.key === "," || event.key === "Enter") {
        event.preventDefault();
        commitYoutubeDraft(block, valueOf(target));
      } else if (event.key === "Backspace" && !valueOf(target)) {
        const blockState = getBlockState(block);
        blockState.youtubeUrls.pop();
        renderBlock(block);
        syncPage1State(page1Refs());
      }
    });

    block.addEventListener("blur", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || !target.matches("[data-role='youtube-draft']")) {
        return;
      }
      if (valueOf(target).trim()) {
        commitYoutubeDraft(block, valueOf(target));
      }
    }, true);
  }

  function updateBlockStatus(block) {
    const status = findOne(block, ["[data-role='block-status']"]);
    const blockState = getBlockState(block);
    const selectedInstructorName = resolveBlockInstructorName(block, blockState);

    const hasName = Boolean(selectedInstructorName);
    const fileCount = Array.isArray(blockState.files) ? blockState.files.length : 0;
    const vocCount = Array.isArray(blockState.vocFiles) ? blockState.vocFiles.length : 0;
    const youtubeCount = Array.isArray(blockState.youtubeUrls) ? blockState.youtubeUrls.length : 0;
    const hasAssets = fileCount > 0 || youtubeCount > 0 || vocCount > 0;

    block.dataset.valid = String(hasName && hasAssets);
    block.dataset.instructorName = selectedInstructorName;
    if (status) {
      let statusLabel = "";
      if (!hasName && !hasAssets) {
        statusLabel = "자료 없음";
      } else if (hasName && !hasAssets) {
        statusLabel = "자료 대기";
      } else if (!hasName && hasAssets) {
        statusLabel = "강사 선택";
      } else {
        const parts = [];
        if (fileCount > 0) parts.push(`파일 ${fileCount}개`);
        if (youtubeCount > 0) parts.push(`링크 ${youtubeCount}개`);
        if (vocCount > 0) parts.push(`VOC ${vocCount}개`);
        statusLabel = parts.join(" · ");
      }
      status.textContent = statusLabel;
      status.setAttribute("data-instructor-name", selectedInstructorName);
      status.setAttribute("title", hasName ? `${statusLabel} / ${selectedInstructorName}` : statusLabel);
    }
  }

  function resolveBlockInstructorName(block, blockState = getBlockState(block)) {
    const candidates = [
      blockState?.instructorName,
      valueOf(findOne(block, ["[data-role='instructor-name']"])),
      block?.dataset?.instructorName,
    ];
    const trigger = findOne(block, ["[data-action='toggle-instructor-menu']"]);
    if (trigger instanceof HTMLElement) {
      candidates.push(trigger.getAttribute("data-selected-instructor"));
      const title = trigger.getAttribute("title");
      if (title && title !== "강사 선택") {
        candidates.push(title);
      }
    }
    return candidates
      .map((value) => String(value || "").trim())
      .find(Boolean) || "";
  }

  function currentCourseInstructorNamesForCourse(courseId) {
    const normalizedCourseId = String(courseId || "").trim();
    const course = state.page1.courses.find((item) => item.id === normalizedCourseId)
      || (state.page1.selectedCourse?.id === normalizedCourseId ? state.page1.selectedCourse : null);
    return Array.isArray(course?.instructor_names) ? course.instructor_names : [];
  }

  function resolveRestoredInstructorName(rawName, courseId, fallbackIndex = 0, usedNames = new Set()) {
    const normalizedName = String(rawName || "").trim();
    const roster = currentCourseInstructorNamesForCourse(courseId);
    if (!roster.length) {
      return normalizedName;
    }
    if (normalizedName && roster.includes(normalizedName)) {
      return normalizedName;
    }
    const fallbackCandidates = [];
    const genericMatch = normalizedName.match(/^강사\s*(\d+)$/);
    if (genericMatch) {
      const genericIndex = Number(genericMatch[1]) - 1;
      fallbackCandidates.push(roster[genericIndex] || "");
    }
    fallbackCandidates.push(roster[fallbackIndex] || "");
    if (roster.length === 1) {
      fallbackCandidates.push(roster[0]);
    }
    const resolvedFallback = fallbackCandidates
      .map((name) => String(name || "").trim())
      .find((name) => name && !usedNames.has(name));
    return resolvedFallback || normalizedName;
  }

  function getInstructorManifest() {
    return state.page1.blocks
      .filter((block) => block.dataset.blockId)
      .map((block) => ({ id: block.dataset.blockId }));
  }

  function canSubmitAnalysis() {
    if (state.page1.isPreparingAnalysis) {
      return false;
    }
    if (!state.page1.selectedCourseId || state.page1.restoringCourseId === state.page1.selectedCourseId) {
      return false;
    }
    const validBlocks = state.page1.blocks.filter((block) => block.dataset.valid === "true");
    return validBlocks.length >= 1;
  }

  function normalizeCoursePayload(course) {
    return {
      ...course,
      instructor_names: Array.isArray(course?.instructor_names)
        ? course.instructor_names.map((item) => String(item || "").trim()).filter(Boolean)
        : [],
      sections: Array.isArray(course?.sections) ? course.sections : [],
    };
  }

  function page1Refs() {
    return {
      courseModal: $(SELECTORS.courseModal),
      courseListPanel: $(SELECTORS.courseListPanel),
      courseForm: $(SELECTORS.courseForm),
      analysisForm: $(SELECTORS.analysisForm),
      workspace: $(SELECTORS.page1Workspace),
      emptyState: $(SELECTORS.page1EmptyState),
      blocksRoot: $(SELECTORS.instructorBlocks),
      template: $(SELECTORS.instructorBlockTemplate),
      addBlockButton: $(SELECTORS.addInstructorBlock),
      submitButton: $(SELECTORS.submitAnalysis),
      saveButton: $(SELECTORS.courseSaveButton),
      previewState: $(SELECTORS.coursePreviewState),
      previewTable: $(SELECTORS.coursePreviewTable),
      selectedCourseId: $(SELECTORS.selectedCourseId),
      selectedCourseName: $(SELECTORS.selectedCourseName),
      manifestInput: ensureHiddenInput($(SELECTORS.analysisForm), "instructor_manifest"),
      courseFileInput: findFirst($(SELECTORS.courseForm), ["input[type='file'][name='curriculum_pdf']", "[data-testid='course-curriculum-file']"]),
      courseNameInput: findFirst($(SELECTORS.courseForm), ["input[name='course_name']", "[data-testid='course-name']"]),
      courseFileTokens: $(SELECTORS.courseFileTokens),
      courseInstructorInput: $(SELECTORS.courseInstructorInput),
      courseInstructorTokens: $(SELECTORS.courseInstructorTokens),
      courseInstructorNamesJson: $(SELECTORS.courseInstructorNamesJson),
    };
  }

  function canSaveCourse(refs) {
    const courseName = refs.courseNameInput ? refs.courseNameInput.value.trim() : "";
    syncPreviewSectionsFromTable(refs.previewTable);
    return Boolean(
      courseName
      && state.page1.preview
      && state.page1.previewFile
      && state.page1.draftInstructorNames.length >= 1
      && isSavableCoursePreview(state.page1.preview),
    );
  }

  function updateCourseSaveButtonState(refs) {
    if (refs.courseInstructorNamesJson) {
      refs.courseInstructorNamesJson.value = JSON.stringify(state.page1.draftInstructorNames);
    }
    if (refs.saveButton) {
      setButtonDisabled(refs.saveButton, !canSaveCourse(refs));
    }
  }

  function handleCourseFileSelection(refs) {
    const file = refs.courseFileInput?.files?.[0] || null;
    setCourseDraftFile(file, refs);
  }

  function setCourseDraftFile(file, refs) {
    if (!file) {
      clearCourseDraftFile(refs);
      return;
    }
    state.page1.preview = null;
    state.page1.previewFile = file;
    replaceSingleFile(refs.courseFileInput, file);
    renderCourseFileTokens(refs);
    previewCourse(refs.courseForm, refs.courseFileInput, refs.courseNameInput, refs.previewState, refs.previewTable, refs.saveButton).then(() => {
      updateCourseSaveButtonState(refs);
    });
  }

  function clearCourseDraftFile(refs) {
    state.page1.preview = null;
    state.page1.previewFile = null;
    replaceSingleFile(refs.courseFileInput, null);
    const sectionsInput = $("#course-sections-json");
    const rawTextInput = $("#course-raw-curriculum-text");
    if (sectionsInput) {
      sectionsInput.value = "[]";
    }
    if (rawTextInput) {
      rawTextInput.value = "";
    }
    if (refs.previewTable) {
      refs.previewTable.innerHTML = "";
      refs.previewTable.classList.add("is-hidden");
    }
    refs.previewState?.classList.remove("is-success", "is-warning", "is-danger");
    renderCourseFileTokens(refs);
    setStatus(refs.previewState, "PDF를 업로드하면 과정 초안이 준비됩니다.");
    updateCourseSaveButtonState(refs);
  }

  function renderCourseFileTokens(refs) {
    if (!refs.courseFileTokens) {
      return;
    }
    refs.courseFileTokens.innerHTML = "";
    if (!state.page1.previewFile) {
      return;
    }
    refs.courseFileTokens.appendChild(createChip(state.page1.previewFile.name, {
      removeAttr: "data-remove-course-file",
      removeValue: "0",
    }));
  }

  function commitCourseInstructorDraft(rawValue, refs) {
    const nextValues = String(rawValue || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!nextValues.length) {
      refs.courseInstructorInput.value = "";
      return;
    }
    nextValues.forEach((name) => {
      if (!state.page1.draftInstructorNames.includes(name)) {
        state.page1.draftInstructorNames.push(name);
      }
    });
    refs.courseInstructorInput.value = "";
    renderCourseInstructorTokens(refs);
    updateCourseSaveButtonState(refs);
  }

  function renderCourseInstructorTokens(refs) {
    if (!refs.courseInstructorTokens) {
      return;
    }
    refs.courseInstructorTokens.innerHTML = "";
    state.page1.draftInstructorNames.forEach((name, index) => {
      refs.courseInstructorTokens.appendChild(createChip(name, {
        removeAttr: "data-remove-course-instructor",
        removeValue: String(index),
      }));
    });
    if (refs.courseInstructorNamesJson) {
      refs.courseInstructorNamesJson.value = JSON.stringify(state.page1.draftInstructorNames);
    }
  }

  function resetCourseDraft(refs) {
    state.page1.preview = null;
    state.page1.previewFile = null;
    state.page1.draftInstructorNames = [];
    if (refs.courseForm) {
      refs.courseForm.reset();
    }
    if (refs.previewTable) {
      refs.previewTable.innerHTML = "";
      refs.previewTable.classList.add("is-hidden");
    }
    const sectionsInput = $("#course-sections-json");
    const rawTextInput = $("#course-raw-curriculum-text");
    if (sectionsInput) {
      sectionsInput.value = "[]";
    }
    if (rawTextInput) {
      rawTextInput.value = "";
    }
    renderCourseFileTokens(refs);
    renderCourseInstructorTokens(refs);
    refs.previewState?.classList.remove("is-success", "is-warning", "is-danger");
    setStatus(refs.previewState, "PDF를 업로드하면 과정 초안이 준비됩니다.");
    updateCourseSaveButtonState(refs);
  }

  function resetPage1Blocks(blocksRoot, template, analysisForm, manifestInput) {
    rebuildPage1Blocks(blocksRoot, template, analysisForm, manifestInput, [createEmptyDraftBlock()]);
  }

  function rebuildPage1Blocks(blocksRoot, template, analysisForm, manifestInput, snapshots = []) {
    if (!blocksRoot) {
      return;
    }
    blocksRoot.innerHTML = "";
    state.page1.blocks = [];
    state.page1.blockData = {};
    state.page1.menuOpenBlockId = "";
    state.page1.instructorMenuOpenBlockId = "";
    const blockSnapshots = Array.isArray(snapshots) && snapshots.length ? snapshots : [createEmptyDraftBlock()];
    blockSnapshots.forEach((snapshot, index) => {
      const blockId = uniqueId("instructor");
      const block = createInstructorBlock(blockId, index + 1, template);
      blocksRoot.appendChild(block);
      state.page1.blocks.push(block);
      bindInstructorBlock(block, index + 1);
      const blockState = getBlockState(block);
      blockState.mode = snapshot?.mode === "youtube" ? "youtube" : "files";
      if (snapshot?.mode === "voc") {
        blockState.mode = "voc";
      }
      blockState.instructorName = String(snapshot?.instructorName || "").trim();
      blockState.files = Array.isArray(snapshot?.files) ? snapshot.files.slice() : [];
      blockState.vocFiles = Array.isArray(snapshot?.vocFiles) ? snapshot.vocFiles.slice() : [];
      blockState.youtubeUrls = Array.isArray(snapshot?.youtubeUrls) ? snapshot.youtubeUrls.slice() : [];
      renderBlock(block);
    });
    if (analysisForm && manifestInput) {
      manifestInput.value = JSON.stringify(getInstructorManifest(), null, 0);
    }
  }

  function getBlockState(block) {
    const blockId = block?.dataset?.blockId || "";
    state.page1.blockData[blockId] = state.page1.blockData[blockId] || {
      mode: "files",
      instructorName: "",
      files: [],
      vocFiles: [],
      youtubeUrls: [],
    };
    return state.page1.blockData[blockId];
  }

  function renderBlock(block) {
    if (!(block instanceof HTMLElement)) {
      return;
    }
    const blockState = getBlockState(block);
    const trigger = findOne(block, ["[data-action='toggle-mode-menu']"]);
    const menu = findOne(block, ["[data-role='mode-menu']"]);
    const filesSurface = findOne(block, ["[data-role='files-surface']"]);
    const youtubeSurface = findOne(block, ["[data-role='youtube-surface']"]);
    const youtubeDraft = findOne(block, ["[data-role='youtube-draft']"]);
    const youtubeHidden = findOne(block, ["[data-role='instructor-youtube']"]);
    const vocSurface = findOne(block, ["[data-role='voc-surface']"]);
    const vocHidden = findOne(block, ["[data-role='instructor-voc']"]);
    const assetRail = findOne(block, ["[data-role='asset-rail']"]);
    const assetList = findOne(block, ["[data-role='asset-list']"]);
    const instructorInput = findOne(block, ["[data-role='instructor-name']"]);
    const instructorTrigger = findOne(block, ["[data-action='toggle-instructor-menu']"]);
    const instructorMenu = findOne(block, ["[data-role='instructor-menu']"]);
    const activeSurface = blockState.mode === "voc" ? vocSurface : filesSurface;
    const activeTap = activeSurface ? findOne(activeSurface, ["[data-action='open-file-picker']"]) : null;

    if (trigger) {
      trigger.classList.toggle("is-youtube", blockState.mode === "youtube");
      if (blockState.mode !== "youtube") {
        trigger.textContent = "+";
      } else {
        trigger.textContent = "";
      }
    }
    if (menu) {
      menu.hidden = state.page1.menuOpenBlockId !== block.dataset.blockId;
    }
    if (filesSurface) {
      filesSurface.hidden = blockState.mode !== "files";
    }
    if (youtubeSurface) {
      youtubeSurface.hidden = blockState.mode !== "youtube";
    }
    if (vocSurface) {
      vocSurface.hidden = blockState.mode !== "voc";
    }
    if (youtubeHidden) {
      youtubeHidden.value = blockState.youtubeUrls.join("\n");
    }
    if (youtubeDraft) {
      youtubeDraft.value = youtubeDraft.value || "";
    }
    if (assetList) {
      renderBlockAssets(block, assetList, assetRail);
    }
    updateBlockPrompts(block, activeTap, youtubeDraft, blockState);
    if (instructorInput && instructorTrigger && instructorMenu) {
      populateBlockInstructorMenu(block, instructorInput, instructorTrigger, instructorMenu);
    }
    syncBlockFileInput(block);
    updateBlockStatus(block);
  }

  function updateBlockPrompts(block, fileTap, youtubeDraft, blockState) {
    const hasCourse = Boolean(state.page1.selectedCourseId);
    if (fileTap) {
      const prompt = blockState.mode === "voc" ? "강의평가서(VOC)" : "강의 자료";
      fileTap.textContent = hasCourse
        ? `${prompt}를 드래그하거나 클릭해 업로드`
        : "과정을 먼저 선택하거나 추가하세요";
    }
    if (youtubeDraft) {
      youtubeDraft.placeholder = hasCourse
        ? "유튜브 링크를 입력하고 콤마를 누르세요"
        : "과정을 먼저 선택하거나 추가하세요";
    }
    block.dataset.empty = String(!hasCourse);
    block.dataset.mode = blockState.mode;
  }

  function renderBlockAssets(block, container, rail) {
    const blockState = getBlockState(block);
    container.innerHTML = "";
    blockState.files.forEach((file, index) => {
      container.appendChild(createChip(file.name, {
        kind: "file",
        removeAttr: "data-remove-file-index",
        removeValue: String(index),
      }));
    });
    const vocFiles = Array.isArray(blockState.vocFiles) ? blockState.vocFiles : [];
    vocFiles.forEach((file, index) => {
      container.appendChild(createChip(file.name, {
        kind: "voc",
        removeAttr: "data-remove-voc-index",
        removeValue: String(index),
      }));
    });
    blockState.youtubeUrls.forEach((url, index) => {
      container.appendChild(createChip(url, {
        kind: "youtube",
        removeAttr: "data-remove-youtube-index",
        removeValue: String(index),
      }));
    });
    if (rail) {
      rail.hidden = !container.children.length;
    }
  }

  function populateBlockInstructorMenu(block, input, trigger, menu) {
    const roster = currentCourseInstructorNames();
    const blockState = getBlockState(block);
    if (blockState.instructorName && !roster.includes(blockState.instructorName)) {
      blockState.instructorName = "";
    }
    const usedNames = new Set(
      state.page1.blocks
        .filter((item) => item !== block)
        .map((item) => getBlockState(item).instructorName)
        .filter(Boolean),
    );
    input.value = blockState.instructorName || "";
    block.dataset.instructorName = blockState.instructorName || "";
    trigger.classList.toggle(CSS.active, Boolean(blockState.instructorName));
    trigger.setAttribute("aria-expanded", String(state.page1.instructorMenuOpenBlockId === block.dataset.blockId));
    trigger.setAttribute("title", blockState.instructorName || "강사 선택");
    trigger.setAttribute("aria-label", blockState.instructorName ? `강사 선택됨: ${blockState.instructorName}` : "강사 선택");
    trigger.setAttribute("data-selected-instructor", blockState.instructorName || "");
    menu.hidden = state.page1.instructorMenuOpenBlockId !== block.dataset.blockId;
    menu.innerHTML = "";

    if (!roster.length) {
      const empty = document.createElement("div");
      empty.className = "instructor-picker-menu__empty";
      empty.textContent = "등록 강사 없음";
      menu.appendChild(empty);
      return;
    }

    const resetButton = document.createElement("button");
    resetButton.type = "button";
    resetButton.className = "instructor-picker-menu__item";
    resetButton.textContent = "선택 해제";
    resetButton.setAttribute("data-action", "select-instructor");
    resetButton.setAttribute("data-instructor-value", "");
    resetButton.classList.toggle(CSS.selected, !blockState.instructorName);
    menu.appendChild(resetButton);

    roster.forEach((name) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "instructor-picker-menu__item";
      option.textContent = name;
      option.setAttribute("data-action", "select-instructor");
      option.setAttribute("data-instructor-value", name);
      option.disabled = usedNames.has(name);
      option.classList.toggle(CSS.selected, blockState.instructorName === name);
      menu.appendChild(option);
    });
  }

  function currentCourseInstructorNames() {
    return currentCourseInstructorNamesForCourse(state.page1.selectedCourse?.id || "");
  }

  function toggleModeMenu(block) {
    const blockId = block.dataset.blockId || "";
    state.page1.menuOpenBlockId = state.page1.menuOpenBlockId === blockId ? "" : blockId;
    state.page1.instructorMenuOpenBlockId = "";
    state.page1.blocks.forEach((item) => renderBlock(item));
  }

  function toggleInstructorMenu(block) {
    const blockId = block.dataset.blockId || "";
    state.page1.instructorMenuOpenBlockId = state.page1.instructorMenuOpenBlockId === blockId ? "" : blockId;
    state.page1.menuOpenBlockId = "";
    state.page1.blocks.forEach((item) => renderBlock(item));
  }

  function closeAllBlockMenus() {
    if (!state.page1.menuOpenBlockId && !state.page1.instructorMenuOpenBlockId) {
      return;
    }
    state.page1.menuOpenBlockId = "";
    state.page1.instructorMenuOpenBlockId = "";
    state.page1.blocks.forEach((block) => renderBlock(block));
  }

  function switchBlockMode(block, mode) {
    const blockState = getBlockState(block);
    if (mode === "youtube") {
      blockState.mode = "youtube";
    } else if (mode === "voc") {
      blockState.mode = "voc";
    } else {
      blockState.mode = "files";
    }
    state.page1.menuOpenBlockId = "";
    state.page1.instructorMenuOpenBlockId = "";
    renderBlock(block);
  }

  function addBlockFiles(block, files, type = "files") {
    const blockState = getBlockState(block);
    const nextFiles = Array.isArray(files) ? files.filter(Boolean) : [];
    if (!nextFiles.length) {
      return;
    }
    const targetArr = type === "voc" ? blockState.vocFiles : blockState.files;
    const seen = new Set(targetArr.map(fileIdentity));
    nextFiles.forEach((file) => {
      const identity = fileIdentity(file);
      if (!seen.has(identity)) {
        targetArr.push(file);
        seen.add(identity);
      }
    });
    renderBlock(block);
    syncPage1State(page1Refs());
  }

  function removeBlockFile(block, index, type = "files") {
    const blockState = getBlockState(block);
    if (Number.isNaN(index)) {
      return;
    }
    const targetArr = type === "voc" ? blockState.vocFiles : blockState.files;
    targetArr.splice(index, 1);
    renderBlock(block);
    syncPage1State(page1Refs());
  }

  function commitYoutubeDraft(block, rawValue) {
    const blockState = getBlockState(block);
    const nextUrls = String(rawValue || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!nextUrls.length) {
      return;
    }
    nextUrls.forEach((url) => {
      if (!blockState.youtubeUrls.includes(url)) {
        blockState.youtubeUrls.push(url);
      }
    });
    const draftInput = findOne(block, ["[data-role='youtube-draft']"]);
    if (draftInput) {
      draftInput.value = "";
    }
    renderBlock(block);
    syncPage1State(page1Refs());
  }

  function removeBlockYoutubeUrl(block, index) {
    const blockState = getBlockState(block);
    if (Number.isNaN(index)) {
      return;
    }
    blockState.youtubeUrls.splice(index, 1);
    renderBlock(block);
    syncPage1State(page1Refs());
  }

  function syncBlockFileInput(block) {
    const fileInput = findOne(block, ["[data-role='instructor-files']"]);
    const vocInput = findOne(block, ["[data-role='instructor-voc']"]);
    const blockState = getBlockState(block);

    if (fileInput) {
      setFilesOnInput(fileInput, blockState.files);
    }
    if (vocInput) {
      setFilesOnInput(vocInput, blockState.vocFiles);
    }
  }

  function setBlockDisabled(block, disabled) {
    block.classList.toggle(CSS.disabled, disabled);
    qsa("button, input, select", block).forEach((element) => {
      if (element.matches("[data-role='instructor-files']")) {
        element.disabled = disabled;
        return;
      }
      element.disabled = disabled;
    });
  }

  function canAcceptBlockFileDrop(block) {
    if (!(block instanceof HTMLElement)) {
      return false;
    }
    if (!state.page1.selectedCourseId || state.page1.restoringCourseId === state.page1.selectedCourseId) {
      return false;
    }
    return !block.classList.contains(CSS.disabled);
  }

  function canAddMoreBlocks() {
    const roster = currentCourseInstructorNames();
    if (!state.page1.selectedCourseId || state.page1.restoringCourseId === state.page1.selectedCourseId) {
      return false;
    }
    return roster.length > state.page1.blocks.length;
  }

  function replaceSingleFile(input, file) {
    if (!input) {
      return;
    }
    setFilesOnInput(input, file ? [file] : []);
  }

  function setFilesOnInput(input, files) {
    if (!input) {
      return;
    }
    if (typeof DataTransfer !== "function") {
      return;
    }
    const transfer = new DataTransfer();
    (Array.isArray(files) ? files : []).forEach((file) => {
      if (file) {
        transfer.items.add(file);
      }
    });
    input.files = transfer.files;
  }

  function bindDropzone(node, options = {}) {
    if (!node) {
      return;
    }
    const onFiles = typeof options.onFiles === "function" ? options.onFiles : () => { };
    const canAccept = typeof options.canAccept === "function" ? options.canAccept : () => true;
    const hasTransferFiles = (event) => {
      const dataTransfer = event?.dataTransfer;
      if (!dataTransfer) {
        return false;
      }
      if ((dataTransfer.files?.length || 0) > 0) {
        return true;
      }
      return Array.from(dataTransfer.types || []).includes("Files");
    };
    ["dragenter", "dragover"].forEach((eventName) => {
      node.addEventListener(eventName, (event) => {
        if (!hasTransferFiles(event)) {
          return;
        }
        event.preventDefault();
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = canAccept(event) ? "copy" : "none";
        }
        node.classList.toggle("is-dragover", canAccept(event));
      });
    });
    ["dragleave", "dragend"].forEach((eventName) => {
      node.addEventListener(eventName, () => {
        node.classList.remove("is-dragover");
      });
    });
    node.addEventListener("drop", (event) => {
      if (!hasTransferFiles(event)) {
        return;
      }
      event.preventDefault();
      node.classList.remove("is-dragover");
      if (!canAccept(event)) {
        return;
      }
      const files = Array.from(event.dataTransfer?.files || []);
      if (files.length) {
        onFiles(files);
      }
    });
  }

  function createChip(label, options = {}) {
    const chip = document.createElement("span");
    chip.className = "lane-chip";
    if (options.kind) {
      chip.dataset.kind = options.kind;
      const kind = document.createElement("span");
      kind.className = `lane-chip__kind lane-chip__kind-${options.kind}`;
      kind.textContent = options.kind === "youtube" ? "YT" : "파일";
      chip.appendChild(kind);
    }
    const text = document.createElement("span");
    text.className = "lane-chip__label";
    text.textContent = label;
    chip.appendChild(text);
    if (options.removeAttr) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "lane-chip__remove";
      remove.textContent = "×";
      remove.setAttribute(options.removeAttr, options.removeValue || "");
      chip.appendChild(remove);
    }
    return chip;
  }

  function fileIdentity(file) {
    return `${file.name}:${file.size}:${file.lastModified}`;
  }

  function renderPage2Charts(containers, options = {}) {
    if (!state.page2.result) {
      return;
    }
    const result = state.page2.result;
    const sections = Array.isArray(result.course?.sections) ? result.course.sections : (result.sections || []);
    const instructors = Array.isArray(result.instructors) ? result.instructors : [];
    const selected = getSelectedInstructorRecord(instructors);
    state.page2.instructorIndex = selected.index;
    state.page2.instructorName = selected.instructor ? selected.instructor.name : "";

    if (options.syncSelection !== false) {
      setTextForTargets(containers.selectedInstructorTargets, state.page2.instructorName || "미선택");
      syncInstructorButtons(qsa(joinSelectors(SELECTORS.page2InstructorButtons)), state.page2.instructorIndex, state.page2.instructorName);
      syncModeButtons(qsa(joinSelectors(SELECTORS.page2ModeButtons)));
    }

    const roseByMode = result.rose_series_by_mode?.[state.page2.mode]
      || result.rose_series_by_mode?.combined
      || {};
    const legacyRoseData = result.rose_series_by_instructor?.[state.page2.instructorName]
      || selected.instructor?.section_coverages?.map((coverage) => ({
        name: coverage.section_title,
        value: Math.round((coverage.token_share || 0) * 10000) / 100,
      }))
      || [];
    const roseData = roseByMode[state.page2.instructorName] || legacyRoseData;
    const keywordsByMode = result.keywords_by_mode?.[state.page2.mode]
      || result.keywords_by_mode?.combined
      || result.keywords_by_instructor
      || {};
    const wordCloudData = (keywordsByMode[state.page2.instructorName] || []).map((item, index) => ({
      name: item.text,
      value: item.value,
      textStyle: {
        color: stableColorForKey(item.text || String(index)),
      },
    }));
    const modeData = result.mode_series?.[state.page2.mode] || result.mode_series?.combined || {};
    const averageSeries = Array.isArray(modeData.average) ? modeData.average : [];
    const instructorSeries = modeData.instructors || {};
    const lineSeries = result.line_series_by_mode?.[state.page2.mode] || result.line_series_by_mode?.combined || {};
    const compareNames = resolveComparisonNames(lineSeries.instructors || {}, instructors);

    if (options.updateRoseWordcloud !== false) {
      renderChartOrFallback(containers.rose, "rose", buildRoseOption(sections, roseData));
      renderChartOrFallback(containers.wordcloud, "wordcloud", buildWordCloudOption(wordCloudData));
    }

    if (options.updateModeCharts !== false) {
      renderChartOrFallback(containers.averageBar, "average-bar", buildAverageBarOption(sections, averageSeries));
      renderChartOrFallback(containers.instructorBar, "instructor-bar", buildInstructorBarOption(sections, instructors, instructorSeries));
    }

    if (options.updateLine !== false) {
      renderChartOrFallback(containers.line, "comparison", buildComparisonOption(sections, lineSeries, compareNames));
    }
  }

  function updatePage2Charts(containers, options = {}) {
    renderPage2Charts(containers, options);
  }

  function buildRoseOption(sections, data) {
    const roseData = (data.length
      ? data
      : sections.map((section) => ({
        name: section.title,
        value: 0,
      }))
    ).sort((left, right) => Number(right.value || 0) - Number(left.value || 0));

    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "item" },
      legend: {
        orient: "vertical",
        left: "4%",
        top: "middle",
        itemWidth: 12,
        itemHeight: 12,
        textStyle: {
          color: "#475569",
          fontSize: 12,
          fontWeight: 600,
        },
      },
      series: [
        {
          name: "강의 비중",
          type: "pie",
          radius: ["58%", "82%"],
          center: ["68%", "48%"],
          itemStyle: {
            borderRadius: 10,
            borderColor: "#fff",
            borderWidth: 2,
          },
          label: {
            show: true,
            position: "outside",
            formatter: "{b}\n({d}%)",
            color: "#475569",
            fontWeight: 600,
          },
          labelLine: {
            show: true,
            length: 15,
            length2: 10,
          },
          data: roseData.map((item, index) => ({
            name: item.name || sections[index]?.title || `대주제 ${index + 1}`,
            value: Math.round(Number(item.value || 0) * 10) / 10,
            itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length] },
          })),
        },
      ],
    };
  }

  function buildWordCloudOption(data) {
    const items = data.length ? data : [{ name: "데이터 없음", value: 1 }];
    return {
      tooltip: { show: items[0]?.name !== "데이터 없음" },
      series: [
        {
          type: "wordCloud",
          shape: "circle",
          gridSize: 8,
          sizeRange: [18, 54],
          rotationRange: [0, 0],
          textStyle: {
            color: (params) => stableColorForKey(params?.name || params?.data?.name || params?.value || "word"),
            fontWeight: 800,
          },
          data: items.map((item, index) => ({
            name: item.name,
            value: item.value,
            textStyle: {
              color: stableColorForKey(item.name || String(index)),
            },
          })),
        },
      ],
    };
  }

  function buildAverageBarOption(sections, seriesItems) {
    const safeItems = seriesItems.length ? seriesItems : sections.map((section) => ({
      section_id: section.id,
      section_title: section.title,
      share: 0,
    }));
    return {
      tooltip: { trigger: "item" },
      legend: {
        bottom: 0,
        type: "scroll",
      },
      grid: { left: 70, right: 8, top: 12, bottom: 48, containLabel: false },
      xAxis: { type: "value", max: 100, show: false },
      yAxis: {
        type: "category",
        data: ["전체 평균"],
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#475569", fontWeight: 700 },
      },
      series: safeItems.map((item, index) => ({
        name: item.section_title || sections[index]?.title || `대주제 ${index + 1}`,
        type: "bar",
        stack: "average",
        barWidth: 28,
        data: [Math.round((item.share || 0) * 10000) / 100],
        label: {
          show: true,
          position: "inside",
          color: "#fff",
          fontSize: 11,
          formatter: "{c}%",
        },
        itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length], borderRadius: 999 },
      })),
    };
  }

  function buildInstructorBarOption(sections, instructors, seriesByInstructor) {
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: {
        top: 0,
        type: "scroll",
      },
      grid: { left: 86, right: 8, top: 38, bottom: 20, containLabel: false },
      xAxis: { type: "value", max: 100, show: false },
      yAxis: {
        type: "category",
        data: instructors.map((item) => item.name),
        axisLine: { show: true, lineStyle: { color: "#dbe7db" } },
        axisTick: { show: false },
        axisLabel: { color: "#475569", fontWeight: 700 },
      },
      series: sections.map((section, index) => ({
        name: section.title,
        type: "bar",
        stack: "instructors",
        barWidth: 26,
        data: instructors.map((instructor) => {
          const series = seriesByInstructor[instructor.name] || [];
          const item = series.find((entry) => entry.section_id === section.id);
          return Math.round((item?.share || 0) * 10000) / 100;
        }),
        label: {
          show: true,
          position: "inside",
          color: "#fff",
          fontSize: 10,
          formatter: "{c}%",
        },
        itemStyle: { color: CHART_COLORS[index % CHART_COLORS.length], borderRadius: 999 },
      })),
    };
  }

  function buildComparisonOption(sections, lineSeries, compareNames) {
    const labels = sections.map((item) => item.title);
    const targetValues = labels.map((_, index) => Math.round((lineSeries.target?.[index]?.share || 0) * 10000) / 100);
    const selectedNames = compareNames.length ? compareNames : Object.keys(lineSeries.instructors || {});
    const radarSeries = [
      {
        value: targetValues,
        name: "목표 (강의계획서)",
        itemStyle: { color: "#ff7b7b" },
        lineStyle: { type: "dashed", width: 2 },
        areaStyle: { opacity: 0.08 },
      },
      ...selectedNames.map((name) => ({
        value: labels.map((_, index) => Math.round((lineSeries.instructors?.[name]?.[index]?.share || 0) * 10000) / 100),
        name,
        itemStyle: { color: stableColorForKey(name) },
        lineStyle: { width: 3 },
        areaStyle: { opacity: 0.08 },
      })),
    ];

    return {
      tooltip: {
        trigger: "item",
        formatter(params) {
          const items = Array.isArray(params.value) ? params.value : [];
          return `<strong>${params.name}</strong><br>${items.map((value, index) => `${labels[index]}: ${Number(value || 0).toFixed(1)}%`).join("<br>")}`;
        },
      },
      legend: {
        bottom: 0,
        type: "scroll",
      },
      radar: {
        radius: "62%",
        indicator: labels.map((label) => ({ name: label, max: 100 })),
        splitArea: {
          areaStyle: {
            color: ["rgba(255,255,255,0.92)", "rgba(246,251,246,0.96)"],
          },
        },
        axisName: {
          color: "#1e293b",
          fontSize: 12,
          fontWeight: 600,
        },
      },
      series: [
        {
          type: "radar",
          symbolSize: 6,
          data: radarSeries,
        },
      ],
    };
  }

  function renderChartOrFallback(container, kind, option) {
    if (!container) {
      return;
    }
    if (window.echarts && typeof window.echarts.init === "function") {
      try {
        const instance = state.page2.charts.get(container) || window.echarts.init(container);
        instance.setOption(option, true);
        state.page2.charts.set(container, instance);
        return;
      } catch (error) {
        // Fall through to a simple readable fallback if a chart type is unavailable.
        container.innerHTML = "";
      }
    }

    renderFallbackVisual(container, kind, option);
  }

  function renderFallbackVisual(container, kind, option) {
    container.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "chart-fallback";
    if (kind === "wordcloud") {
      const items = option.series?.[0]?.data || [];
      items.slice(0, 20).forEach((item) => {
        const chip = document.createElement("span");
        chip.className = "chart-fallback-chip";
        chip.textContent = item.name;
        chip.style.fontSize = `${Math.max(12, Math.min(30, 12 + Number(item.value || 0) * 1.5))}px`;
        wrapper.appendChild(chip);
      });
    } else if (kind === "rose") {
      const items = option.series?.[0]?.data || [];
      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${Number(item.value || 0).toFixed(1)}%`;
        wrapper.appendChild(row);
      });
    } else if (kind === "line") {
      const series = option.series || [];
      series.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${(item.data || []).map((value) => Number(value || 0).toFixed(1)).join(" · ")}`;
        wrapper.appendChild(row);
      });
    } else if (kind === "comparison") {
      const series = option.series?.[0]?.data || [];
      series.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${(item.value || []).map((value) => Number(value || 0).toFixed(1)).join(" · ")}`;
        wrapper.appendChild(row);
      });
    } else {
      const series = option.series || [];
      series.forEach((item) => {
        const row = document.createElement("div");
        row.className = "chart-fallback-row";
        row.textContent = `${item.name}: ${(item.data || []).map((value) => Number(value || 0).toFixed(1)).join(" · ")}`;
        wrapper.appendChild(row);
      });
    }
    container.appendChild(wrapper);
  }

  function resizeCharts() {
    state.page2.charts.forEach((instance) => {
      if (instance && typeof instance.resize === "function") {
        instance.resize();
      }
    });
  }

  function renderInsights(root, result) {
    root.innerHTML = "";
    const cards = Array.isArray(result.insights) ? result.insights : [];
    cards.forEach((card, index) => {
      const article = document.createElement("article");
      article.className = "insight-card";
      article.dataset.insightCard = String(index);
      article.innerHTML = `
        <div class="insight-card-head">
          <span class="insight-icon" aria-hidden="true">${iconSvg(card.icon)}</span>
          <div>
            <h3>${escapeHtml(card.title || `인사이트 ${index + 1}`)}</h3>
            <p>${escapeHtml(card.category || "insight")}</p>
          </div>
        </div>
        <p class="insight-issue">${escapeHtml(card.issue || "")}</p>
        <p class="insight-evidence">${escapeHtml(card.evidence || "")}</p>
        <p class="insight-recommendation">${escapeHtml(card.recommendation || "")}</p>
      `;
      root.appendChild(article);
    });
    const trendMeta = trendStatusMeta(result.external_trends_status);
    const footer = document.createElement("div");
    footer.className = `trend-status ${trendMeta.className}`;
    footer.textContent = trendMeta.message;
    root.appendChild(footer);
  }

  function trendStatusMeta(status) {
    const normalized = String(status || "").trim().toLowerCase();
    if (normalized === "planned" || normalized === "pending") {
      return {
        className: "is-planned",
        message: "외부 동향 인사이트는 아직 준비 중입니다.",
      };
    }
    if (normalized === "reflected" || normalized === "completed" || normalized === "ready") {
      return {
        className: "is-success",
        message: "외부 동향 인사이트가 결과에 반영되었습니다.",
      };
    }
    if (normalized === "failed" || normalized === "insufficient" || normalized === "unavailable") {
      return {
        className: "is-failed",
        message: "외부 동향을 충분히 수집하지 못해 내부 분석만 표시합니다.",
      };
    }
    return {
      className: "is-unknown",
      message: "외부 동향 상태를 확인 중입니다.",
    };
  }

  function iconSvg(name) {
    const normalized = String(name || "").trim().toLowerCase();
    if (normalized === "target") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M12 4v16M4 12h16M7.5 7.5l9 9M16.5 7.5l-9 9" />
          <circle cx="12" cy="12" r="6" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      `;
    }
    if (normalized === "users") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M16.5 19a4.5 4.5 0 0 0-9 0M9.5 9.5a2.5 2.5 0 1 0 0-.01M18.5 18a3.5 3.5 0 0 0-2.7-3.4M15.5 8.5a2 2 0 1 1 0-.01" />
        </svg>
      `;
    }
    if (normalized === "spark") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="m12 3 1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3Zm6 11 1 2.4L21 17l-2 1-1 2.5-1-2.5-2-1 2-.6 1-2.4ZM5.5 13l.8 1.8L8 15.5l-1.7.7-.8 1.8-.8-1.8L3 15.5l1.7-.7.8-1.8Z" />
        </svg>
      `;
    }
    if (normalized === "refresh") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M20 11a8 8 0 1 1-2.3-5.7M20 4v5h-5" />
        </svg>
      `;
    }
    if (normalized === "lightbulb") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M9 18h6M10 21h4M8.5 14.5c-1.6-1.2-2.5-3.1-2.5-5.2a6 6 0 1 1 12 0c0 2.1-.9 4-2.5 5.2-.8.7-1.3 1.5-1.5 2.5h-4c-.2-1-.7-1.8-1.5-2.5Z" />
        </svg>
      `;
    }
    if (normalized === "trend") {
      return `
        <svg viewBox="0 0 24 24" role="img" focusable="false">
          <path d="M5 17 10 12l3 3 6-7M5 6v11h14" />
        </svg>
      `;
    }
    return `
      <svg viewBox="0 0 24 24" role="img" focusable="false">
        <path d="M12 3v18M3 12h18" />
      </svg>
    `;
  }

  function bindDialog(surface, openSelectors, closeSelectors, onOpen) {
    if (!surface) {
      return;
    }
    qsa(joinSelectors(openSelectors)).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        openSurface(surface);
        if (onOpen) {
          onOpen();
        }
      });
    });
    qsa(joinSelectors(closeSelectors)).forEach((button) => {
      button.addEventListener("click", () => closeSurface(surface));
    });
    surface.addEventListener("click", (event) => {
      if (event.target === surface) {
        closeSurface(surface);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isOpen(surface)) {
        closeSurface(surface);
      }
    });
  }

  function bindPanel(surface, openSelectors, closeSelectors) {
    if (!surface) {
      return;
    }
    qsa(joinSelectors(openSelectors)).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        toggleSurface(surface);
      });
    });
    qsa(joinSelectors(closeSelectors)).forEach((button) => {
      button.addEventListener("click", () => closeSurface(surface));
    });
    surface.addEventListener("click", (event) => {
      if (event.target === surface) {
        closeSurface(surface);
      }
    });
  }

  function openSurface(surface) {
    surface.hidden = false;
    surface.classList.add(CSS.open);
    surface.setAttribute("aria-hidden", "false");
  }

  function closeSurface(surface) {
    surface.hidden = true;
    surface.classList.remove(CSS.open);
    surface.setAttribute("aria-hidden", "true");
  }

  function toggleSurface(surface) {
    if (isOpen(surface)) {
      closeSurface(surface);
    } else {
      openSurface(surface);
    }
  }

  function isOpen(surface) {
    return !surface.hidden && surface.classList.contains(CSS.open);
  }

  function syncModeButtons(buttons) {
    buttons.forEach((button) => {
      const mode = normalizeMode(button.getAttribute("data-view-mode") || button.getAttribute("data-mode-toggle") || button.getAttribute("data-page2-mode"));
      const active = mode === state.page2.mode;
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
      button.setAttribute("aria-pressed", String(active));
      button.title = button.title || mode;
    });
  }

  function syncInstructorButtons(buttons, selectedIndex, selectedName) {
    buttons.forEach((button) => {
      const index = Number(button.getAttribute("data-instructor-index"));
      let active = Number.isInteger(index) && index === selectedIndex;
      if (!active) {
        const name = button.getAttribute("data-instructor-name") || button.getAttribute("data-instructor-id") || button.textContent?.trim();
        active = Boolean(selectedName && name === selectedName);
      }
      button.classList.toggle(CSS.selected, active);
      button.classList.toggle(CSS.active, active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function selectPage2Instructor(target, containers, options = {}) {
    const result = state.page2.result;
    const instructors = Array.isArray(result?.instructors) ? result.instructors : [];
    if (!instructors.length) {
      return;
    }
    const nextIndex = resolveInstructorIndex(target, state.page2.instructorIndex);
    state.page2.instructorIndex = nextIndex;
    state.page2.instructorName = instructors[nextIndex]?.name || instructors[0].name;
    updatePage2Charts(containers, options);
  }

  function syncComparisonSelection(compareInputs, compareAll) {
    const inputs = Array.isArray(compareInputs) ? compareInputs : [];
    state.page2.compareNames = inputs.filter((input) => input.checked).map((input) => input.value);
    if (compareAll) {
      compareAll.checked = Boolean(inputs.length) && inputs.every((input) => input.checked);
    }
  }

  function resolveComparisonNames(seriesByInstructor, instructors) {
    const availableNames = Array.isArray(instructors) ? instructors.map((item) => item.name) : [];
    const seriesNames = Object.keys(seriesByInstructor || {});
    const selectedNames = (state.page2.compareNames || []).filter((name) => seriesNames.includes(name));
    if (selectedNames.length) {
      return selectedNames;
    }
    return availableNames.filter((name) => seriesNames.includes(name));
  }

  function getSelectedInstructorRecord(instructors) {
    if (!instructors.length) {
      return { instructor: null, index: 0 };
    }
    const index = resolveInstructorIndex(state.page2.instructorIndex || state.page2.instructorName, 0);
    return {
      instructor: instructors[index] || instructors[0],
      index,
    };
  }

  function resolveInstructorIndex(value, fallbackIndex = 0) {
    const result = state.page2.result;
    const instructors = Array.isArray(result?.instructors) ? result.instructors : [];
    if (!instructors.length) {
      return 0;
    }
    const numeric = Number(value);
    if (Number.isInteger(numeric)) {
      return wrapIndex(numeric, instructors.length);
    }
    const name = String(value || "").trim();
    if (name) {
      const matchedIndex = instructors.findIndex((item) => item.name === name);
      if (matchedIndex >= 0) {
        return matchedIndex;
      }
    }
    return wrapIndex(fallbackIndex, instructors.length);
  }

  function wrapIndex(index, length) {
    if (!length) {
      return 0;
    }
    return ((index % length) + length) % length;
  }

  function stableColorForKey(key) {
    const value = String(key || "");
    if (!value) {
      return CHART_COLORS[0];
    }
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
      hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
    }
    const palette = CHART_COLORS.slice(1);
    if (!palette.length) {
      return CHART_COLORS[0];
    }
    return palette[hash % palette.length];
  }

  function setTextForTargets(targets, value) {
    (Array.isArray(targets) ? targets : []).forEach((target) => {
      if (target) {
        target.textContent = value;
      }
    });
  }

  function normalizeMode(mode) {
    const value = String(mode || "").toLowerCase();
    if (value.includes("speech") || value.includes("발화")) {
      return "speech";
    }
    if (value.includes("material") || value.includes("자료")) {
      return "material";
    }
    return "combined";
  }

  function fetchCourses() {
    return fetchJson("/courses", { method: "GET" })
      .then((payload) => (Array.isArray(payload.courses) ? payload.courses : []))
      .catch(() => []);
  }

  function fetchJson(url, options) {
    return fetch(url, options).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload.detail || payload.message || response.statusText || "요청 실패";
        throw new Error(detail);
      }
      return payload;
    });
  }

  function ensureRenderedContainer(surface, name, fallbackTag) {
    let container = surface.querySelector(`[data-role='${name}']`);
    if (!container) {
      container = surface.querySelector(`[data-${name}]`);
    }
    if (!container) {
      container = document.createElement(fallbackTag || "div");
      container.dataset.role = name;
      surface.appendChild(container);
    }
    return container;
  }

  function ensureHiddenInput(form, name) {
    if (!form) {
      return null;
    }
    let input = form.querySelector(`input[type='hidden'][name='${name}']`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    return input;
  }

  function setFieldValue(node, value) {
    if (!node) {
      return;
    }
    if ("value" in node) {
      node.value = value;
    } else {
      node.textContent = value;
    }
  }

  function valueOf(node) {
    if (!node) {
      return "";
    }
    if ("value" in node) {
      return node.value || "";
    }
    return node.textContent || "";
  }

  function setStatus(node, message) {
    if (!node) {
      return;
    }
    node.textContent = message;
  }

  function setBusy(button, busy, label) {
    if (!button) {
      return;
    }
    button.disabled = busy;
    if (label) {
      button.dataset.busyLabel = label;
      if (busy) {
        button.dataset.originalLabel = button.dataset.originalLabel || button.textContent || "";
        button.textContent = label;
      } else if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
      }
    }
  }

  function setButtonDisabled(button, disabled) {
    if (button) {
      button.disabled = disabled;
    }
  }

  function courseSaveButton() {
    return $(SELECTORS.courseSaveButton);
  }

  function summaryPreviewWeights(sections) {
    const total = sections.reduce((sum, section) => sum + Number(section.target_weight || 0), 0);
    return `${Math.round(total * 10) / 10}%`;
  }

  function normalizePreview(payload) {
    const sections = Array.isArray(payload.sections) ? payload.sections.map((section, index) => ({
      id: section.id || uniqueId(`section-${index + 1}`),
      title: section.title || `섹션 ${index + 1}`,
      description: section.description || section.title || "",
      target_weight: section.target_weight === null || section.target_weight === undefined || section.target_weight === ""
        ? null
        : Number(section.target_weight),
      weight_source: section.weight_source || "none",
      raw_weight_value: section.raw_weight_value === null || section.raw_weight_value === undefined || section.raw_weight_value === ""
        ? null
        : Number(section.raw_weight_value),
      confidence: Number(section.confidence || 0),
      source_pages: Array.isArray(section.source_pages) ? section.source_pages.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : [],
      source_snippets: Array.isArray(section.source_snippets) ? section.source_snippets.map((item) => String(item || "").trim()).filter(Boolean) : [],
      needs_weight_input: Boolean(section.needs_weight_input),
    })) : [];
    return {
      decision: payload.decision || "review_required",
      document_kind: payload.document_kind || "curriculum_like",
      document_confidence: Number(payload.document_confidence || 0),
      weight_status: payload.weight_status || "missing",
      raw_curriculum_text: payload.raw_curriculum_text || "",
      sections,
      warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
      blocking_reasons: Array.isArray(payload.blocking_reasons) ? payload.blocking_reasons : [],
      evidence: Array.isArray(payload.evidence) ? payload.evidence.map((item) => ({
        page: item?.page === null || item?.page === undefined || item?.page === "" ? null : Number(item.page),
        snippet: String(item?.snippet || "").trim(),
        reason: String(item?.reason || "").trim(),
      })) : [],
    };
  }

  function renderCoursePreviewState(previewState, preview, courseName) {
    if (!previewState || !preview) {
      return;
    }
    const prefix = courseName ? `${courseName} · ` : "";
    previewState.classList.remove("is-success", "is-warning", "is-danger");
    if (preview.decision === "accepted") {
      previewState.textContent = `${prefix}커리큘럼으로 인식되어 저장할 수 있습니다.`;
      previewState.classList.add("is-success");
      return;
    }
    if (preview.decision === "review_required") {
      previewState.textContent = `${prefix}커리큘럼으로 인식했지만 대주제와 비중을 확인한 뒤 저장해 주세요.`;
      previewState.classList.add("is-warning");
      return;
    }
    previewState.textContent = `${prefix}커리큘럼으로 판정되지 않아 저장할 수 없습니다.`;
    previewState.classList.add("is-danger");
  }

  function renderCoursePreviewTable(previewTable, preview) {
    if (!previewTable || !preview) {
      return;
    }
    previewTable.innerHTML = "";
    const shouldShowTable = preview.decision === "review_required" && preview.sections.length;
    if (!shouldShowTable) {
      previewTable.classList.add("is-hidden");
      return;
    }
    previewTable.classList.remove("is-hidden");
    const wrap = document.createElement("div");
    wrap.className = "preview-table-wrap";
    if (shouldShowTable) {
      wrap.appendChild(buildEditablePreviewTable(preview.sections));
    }
    previewTable.appendChild(wrap);
  }

  function buildEditablePreviewTable(sections) {
    const table = document.createElement("table");
    table.className = "course-preview-table";
    table.innerHTML = `
      <thead>
        <tr>
          <th>대주제</th>
          <th>설명</th>
          <th>비중(%)</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector("tbody");
    sections.forEach((section, index) => {
      const row = document.createElement("tr");
      row.dataset.previewRow = String(index);
      row.innerHTML = `
        <td><input type="text" data-preview-field="title" value="${escapeAttr(section.title)}" /></td>
        <td><input type="text" data-preview-field="description" value="${escapeAttr(section.description || section.title || "")}" /></td>
        <td>
          <input
            type="number"
            min="0"
            step="0.1"
            data-preview-field="target_weight"
            placeholder="직접 입력"
            value="${section.target_weight === null || section.target_weight === undefined ? "" : escapeAttr(section.target_weight)}"
          />
        </td>
      `;
      tbody.appendChild(row);
    });
    return table;
  }

  function syncPreviewSectionsFromTable(previewTable) {
    if (!state.page1.preview || !previewTable || state.page1.preview.decision !== "review_required") {
      return;
    }
    const rows = qsa("[data-preview-row]", previewTable);
    if (!rows.length) {
      return;
    }
    state.page1.preview.sections = rows.map((row, index) => {
      const titleInput = findFirst(row, ["[data-preview-field='title']"]);
      const descriptionInput = findFirst(row, ["[data-preview-field='description']"]);
      const weightInput = findFirst(row, ["[data-preview-field='target_weight']"]);
      const rawWeight = valueOf(weightInput).trim();
      const parsedWeight = rawWeight === "" ? null : Number(rawWeight);
      return {
        ...(state.page1.preview.sections[index] || {}),
        id: state.page1.preview.sections[index]?.id || uniqueId(`section-${index + 1}`),
        title: valueOf(titleInput).trim(),
        description: valueOf(descriptionInput).trim() || valueOf(titleInput).trim(),
        target_weight: Number.isFinite(parsedWeight) ? parsedWeight : null,
        needs_weight_input: !(Number.isFinite(parsedWeight) && parsedWeight > 0),
      };
    }).filter((section) => section.title);
    state.page1.preview.weight_status = derivePreviewWeightStatus(state.page1.preview.sections);
    const sectionsInput = $("#course-sections-json");
    if (sectionsInput) {
      sectionsInput.value = JSON.stringify(state.page1.preview.sections);
    }
  }

  function derivePreviewWeightStatus(sections) {
    if (!Array.isArray(sections) || !sections.length) {
      return "missing";
    }
    return sections.every((section) => Number(section.target_weight) > 0) ? "explicit" : "missing";
  }

  function isSavableCoursePreview(preview) {
    if (!preview || preview.decision === "rejected") {
      return false;
    }
    return previewSectionsAreValid(preview.sections);
  }

  function previewSectionsAreValid(sections) {
    return Array.isArray(sections)
      && sections.length > 0
      && sections.every((section) => {
        const title = String(section?.title || "").trim();
        const description = String(section?.description || section?.title || "").trim();
        const targetWeight = Number(section?.target_weight);
        return Boolean(title && description && Number.isFinite(targetWeight) && targetWeight > 0);
      });
  }

  function findOne(root, selectors) {
    return findFirst(root, selectors);
  }

  function joinSelectors(selectors) {
    return selectors.filter(Boolean).join(", ");
  }

  function findFirst(root, selectors) {
    const scope = root && root.querySelector ? root : document;
    return scope.querySelector(joinSelectors(selectors));
  }

  function qsa(selector, root = document) {
    if (!selector) {
      return [];
    }
    return Array.from((root || document).querySelectorAll(selector));
  }

  function $(selector, root = document) {
    return (root || document).querySelector(selector);
  }

  function text(node) {
    return node ? node.textContent || "" : "";
  }

  function formatPrepareMode(mode) {
    const normalized = String(mode || "").trim().toLowerCase();
    if (normalized === "openai") {
      return "OpenAI 임베딩";
    }
    if (normalized === "lexical") {
      return "Lexical 기본";
    }
    return normalized || "자동";
  }

  function formatDurationSeconds(seconds) {
    const total = Math.max(0, Number(seconds || 0));
    if (!total) {
      return "0분";
    }
    const hours = Math.floor(total / 3600);
    const minutes = Math.ceil((total % 3600) / 60);
    if (hours <= 0) {
      return `${minutes}분`;
    }
    if (minutes <= 0) {
      return `${hours}시간`;
    }
    return `${hours}시간 ${minutes}분`;
  }

  function formatUsd(value) {
    const amount = Number(value || 0);
    return `$${amount.toFixed(4)}`;
  }

  function safeParseJSON(raw, fallback) {
    if (!raw) {
      return fallback;
    }
    try {
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("`", "&#96;");
  }

  function iconLabel(name) {
    const key = String(name || "").toLowerCase();
    const map = {
      target: "🎯",
      users: "👥",
      spark: "✨",
      refresh: "🔁",
      lightbulb: "💡",
    };
    return map[key] || "💡";
  }

  function uniqueId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `${prefix}-${window.crypto.randomUUID().slice(0, 8)}`;
    }
    return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function debounce(fn, delay) {
    let timer = null;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn(...args), delay);
    };
  }

  function updateCourseListSelectionWhenRendered() {
    updateCourseListSelection($(SELECTORS.courseListPanel));
  }

  window.addEventListener("load", updateCourseListSelectionWhenRendered);
})();
