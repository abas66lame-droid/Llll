// نقطة الدخول لحزمة Firebase المحلية: تُصدَّر كـ window.FB
export { initializeApp } from 'firebase/app';
export { getAuth, signInWithCustomToken, onAuthStateChanged, signOut, connectAuthEmulator, getIdTokenResult } from 'firebase/auth';
export { initializeFirestore, getFirestore, persistentLocalCache, persistentMultipleTabManager, connectFirestoreEmulator,
  collection, doc, query, where, orderBy, limit, onSnapshot, getDoc, getDocs, setDoc, deleteDoc } from 'firebase/firestore';
export { getFunctions, httpsCallable, connectFunctionsEmulator } from 'firebase/functions';
